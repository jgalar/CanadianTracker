from __future__ import annotations

import decimal
import logging
import time
from collections.abc import Iterable, Iterator, Sequence
from datetime import datetime
from typing import Callable, Generator, Optional, Tuple

from curl_cffi import requests

logger = logging.getLogger(__name__)


class _ProductCategory:
    """A category in the store's product hierarchy."""

    def __init__(self, id: str, name: str, subcategories: list[_ProductCategory]):
        self._id = id
        self._name = name
        self._subcategories = subcategories
        self._parent = None

        for sub in self._subcategories:
            sub._parent = self

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def full_name(self) -> str:
        if self._parent:
            return f"{self._parent.full_name} > {self.name}"
        else:
            return self.name

    @property
    def subcategories(self) -> list[_ProductCategory]:
        return self._subcategories

    def visit(self, callback: Callable[[_ProductCategory, int], None], level: int):
        callback(self, level)
        for sub in self.subcategories:
            sub.visit(callback, level + 1)

    def iter_preorder(
        self, level: int
    ) -> Generator[Tuple[_ProductCategory, int], None, None]:
        yield self, level
        for cat in self.subcategories:
            yield from cat.iter_preorder(level + 1)


class _ProductCategories:
    """Collection of product categories forming a tree structure."""

    def __init__(self, categories: list[_ProductCategory]):
        self._categories = categories

    def visit(self, callback: Callable[[_ProductCategory, int], None]):
        for sub in self._categories:
            sub.visit(callback, 1)

    def iter_preorder(self):
        """Iterate on the category tree, in pre-order."""
        for cat in self._categories:
            yield from cat.iter_preorder(1)

    @property
    def categories(self) -> Iterable[_ProductCategory]:
        return self._categories


_base_headers = {
    "accept": "application/json, text/plain, */*",
    "bannerid": "CTR",
    "basesiteid": "CTR",
    "browse-mode": "OFF",
    "dnt": "1",
    "ocp-apim-subscription-key": "c01ef3612328420c9f5cd9277e815a0e",
    "referer": "https://www.canadiantire.ca/",
    "service-client": "ctr/web",
    "service-version": "v1",
    "x-web-host": "www.canadiantire.ca",
}


class Product:
    """A product returned by the Triangle API."""

    def __init__(self, code: str, name: str, is_in_clearance: bool, url: str):
        self._code = code
        self._name = name
        self._is_in_clearance = is_in_clearance
        self._url = url

    @property
    def code(self) -> str:
        return self._code

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_in_clearance(self) -> bool:
        return self._is_in_clearance

    @property
    def url(self) -> str:
        return self._url

    def __repr__(self):
        props = {
            "name": self.name,
            "code": self.code,
            "is_in_clearance": self._is_in_clearance,
        }
        return str(props)


class Sku:
    """A SKU returned by the Triangle API."""

    def __init__(self, code: str, formatted_code: str):
        self._code = code
        self._formatted_code = formatted_code

    @property
    def code(self) -> str:
        return self._code

    @property
    def formatted_code(self) -> str:
        return self._formatted_code

    def __repr__(self):
        props = {
            "code": self.code,
            "formatted_code": self.formatted_code,
        }
        return str(props)


class PriceInfo:
    """Price and availability info for a SKU returned by the Triangle API."""

    def __init__(self, result: dict):
        self._raw_payload = result

    @property
    def price(self) -> decimal.Decimal | None:
        current_price = self._raw_payload["currentPrice"]
        if current_price is None:
            return None

        value = current_price["value"]
        assert type(value) in [decimal.Decimal, int]
        return decimal.Decimal(value)

    @property
    def code(self) -> str:
        return self._raw_payload["code"]

    @property
    def in_promo(self) -> bool:
        return self._raw_payload["priceValidUntil"] is not None

    @property
    def raw_payload(self) -> str:
        return str(self._raw_payload)

    def __repr__(self) -> str:
        return str(self.__dict__)


class ProductInventory(Iterable):
    """Iterates over all products in the store's inventory via the Triangle API."""

    def __init__(
        self,
        category_levels_to_scrape: list[int] | None = None,
        dev_max_categories: int = 0,
        dev_max_pages_per_category: int = 0,
    ):
        self._dev_max_pages_per_category = dev_max_pages_per_category
        self._dev_max_categories = dev_max_categories
        # The Triangle product listing API seems to have an internal limit
        # that prevents listing more than ~10,000 items. To work around this,
        # we list products by category.
        #
        # Categories are hierarchical, for example: automotive,
        # automotive::car-cleaning. Overall, most products seem to belong to
        # a sub-category and to the higher-level categories that contain that
        # category.
        #
        # However, we have seen illogical results, where scraping, say, all level 2
        # categories under automotive, we found more products than by just scraping
        # automotive.  There is therefore some value in scraping all categories, at
        # all levels.  But it would be very expensive to do this every day.  There
        # are 5 levels of categories at the time of writing, so scraping all levels
        # would mean scraping 5 times the number of products.  To find a good
        # balance, the default is to scrape one category level, based on the number
        # of the day.  Note that this is only to discover new products, so at worst
        # it will take a few more days to discover a new product that only appears
        # in a specific category level, for some reason.
        self._categories = self._fetch_categories()
        max_level = 0
        for cat, level in self._categories.iter_preorder():
            logger.debug(f"[{level}] {cat.id} - {cat.full_name}")
            max_level = max(level, max_level)

        if category_levels_to_scrape is None:
            # No category level specified.  Choose one based on the current day.
            self._category_levels_to_scrape = [datetime.now().day % max_level + 1]
        else:
            self._category_levels_to_scrape = category_levels_to_scrape

        logger.debug(f"Category levels to scrape: {self._category_levels_to_scrape}")

    def _fetch_categories(self) -> _ProductCategories:
        """Fetch the list of categories, create some objects out of it."""
        response = requests.get(
            "https://apim.canadiantire.ca/v1/category/api/v1/categories",
            headers=_base_headers,
            params={"lang": "en_CA"},
            impersonate="chrome136",
        )

        if response.status_code != 200:
            logger.error(response.text)
            raise RuntimeError("Failed to get category list")

        def _handle_categories(raw: list[dict]) -> list[_ProductCategory]:
            def _handle_one_category(raw: dict) -> _ProductCategory:
                subcats = _handle_categories(raw["subcategories"])
                return _ProductCategory(raw["id"], raw["name"], subcats)

            cats = []
            for c in raw:
                cats.append(_handle_one_category(c))
            cats.sort(key=lambda category: category.name)
            return cats

        categories = _handle_categories(response.json()["categories"])
        return _ProductCategories(categories)

    @staticmethod
    def _request_page(
        cat: _ProductCategory, cat_level: int, page_number: int = 1
    ) -> requests.Response:
        """Fetch one page of products."""
        return requests.get(
            f"https://apim.canadiantire.ca/v1/search/search?store=64&lang=en_CA&x1=ast-id-level-{cat_level}&q1={cat.id}&experience=category;count=48;page={page_number}",
            headers=_base_headers,
            impersonate="chrome136",
        )

    def __iter__(self) -> Iterator[Product]:
        num_categories_scraped = 0

        for cat, level in self._categories.iter_preorder():
            if level not in self._category_levels_to_scrape:
                continue

            num_categories_scraped += 1

            logger.debug(f"Starting category {cat.full_name}")
            page = 1
            num_pages = None

            while num_pages is None or page < (num_pages + 1):
                logger.debug(
                    f"Fetching listing of category {cat.full_name} (page {page}/{num_pages})"
                )
                try:
                    response = ProductInventory._request_page(
                        cat, level, page_number=page
                    )
                except Exception as e:
                    logger.warning(f"Page request failed with exception: {e}")
                    continue

                response = response.json()

                if num_pages is None:
                    num_pages = int(response["pagination"]["total"])

                for product in response["products"]:
                    assert product["type"] == "PRODUCT"

                    code = product["code"]
                    url = product["url"]
                    name = product["title"]
                    is_in_clearance = "CLEARANCE" in product["badges"]
                    yield Product(code, name, is_in_clearance, url)

                if (
                    self._dev_max_pages_per_category != 0
                    and self._dev_max_pages_per_category == page
                ):
                    break

                page = page + 1

            if (
                self._dev_max_categories != 0
                and self._dev_max_categories == num_categories_scraped
            ):
                break


class NoSuchProductException(RuntimeError):
    """Raised when a product does not exist in the Triangle API."""

    pass


class UnknownProductErrorException(RuntimeError):
    """Raised when an unknown error occurs while fetching a product."""

    pass


class SkusInventory(Iterable):
    """Fetches all SKUs for a given product from the Triangle API."""

    def __init__(self, product_code: str):
        self._product_code = product_code

    @staticmethod
    def _request_page(product_code: str) -> requests.Response:
        """Fetch one product page."""
        headers = _base_headers.copy()
        return requests.get(
            f"https://apim.canadiantire.ca/v1/product/api/v1/product/productFamily/{product_code}?baseStoreId=CTR&lang=en_CA&storeId=64",
            headers=headers,
            timeout=10,
            impersonate="chrome136",
        )

    def __iter__(self):
        for ntry in range(5):
            resp = SkusInventory._request_page(self._product_code)
            if resp.status_code == 404:
                raise NoSuchProductException
            if resp.status_code not in (200, 206):
                logger.error(f"Got status code {resp.status_code} on try {ntry}")
                time.sleep(5)
                continue

            resp = resp.json()
            # Some stale products didn't have a skus list in the response.  The
            # CT website was broken for those, so we just ignore them.
            if "skus" not in resp or resp["skus"] is None:
                return

            for sku in resp["skus"]:
                yield Sku(sku["code"], sku["formattedCode"])

            return

        raise UnknownProductErrorException


class _PriceQueryException(Exception):
    """Raised on a non-200 HTTP response when querying prices."""

    def __init__(self, msg: str, request_status_code: Optional[int] = None):
        super().__init__(msg)
        self._request_status_code = request_status_code

    @property
    def request_status_code(self) -> Optional[int]:
        return self._request_status_code


class PriceFetcher(Iterable):
    """Fetches price info for SKUs in batches from the Triangle API."""

    def __init__(self, sku_codes: Iterator[str]):
        self._sku_codes = sku_codes

    @staticmethod
    def _batches(it: Iterator, batch_max_size: int) -> Generator[list, None, None]:
        batch = []
        for element in it:
            batch.append(element)
            if len(batch) == batch_max_size:
                yield batch
                batch = []

        if len(batch) > 0:
            yield batch

    @staticmethod
    def _request_price_infos(sku_codes: Sequence[str]) -> requests.Response:
        for ntry in range(5):
            url = "https://apim.canadiantire.ca/v1/product/api/v1/product/sku/PriceAvailability/?lang=en_CA&storeId=64"
            headers = _base_headers.copy()
            headers["content-type"] = "application/json"

            body = {
                "skus": [
                    {
                        "code": sku_code,
                        "lowStockThreshold": 0,
                    }
                    for sku_code in sku_codes
                ]
            }

            logger.debug(
                f"Sending batched price info query request: ntry={ntry} batch_size={len(sku_codes)} sku_codes={sku_codes}"
            )
            try:
                response = requests.post(
                    url, headers=headers, json=body, timeout=10, impersonate="chrome136"
                )
            except Exception as e:
                logger.warning(
                    f"Batched price info query request failed with exception: ntry={ntry} batch_size={len(sku_codes)} sku_codes={sku_codes}, exception={e}"
                )
                continue

            if response.status_code != 200:
                # Wait a bit before retrying, in case the admin is restarting the container.
                logger.error(f"Got status code {response.status_code} on try {ntry}")
                logger.error(response.text)

                if "Request failed with status code 404" in response.text:
                    raise _PriceQueryException("Failed to get product info", 404)
                elif response.status_code == 400:
                    raise _PriceQueryException(
                        "Failed to get product info", response.status_code
                    )

                time.sleep(5)
                continue

            return response

        raise _PriceQueryException("Failed to get product info")

    @staticmethod
    def _get_price_infos(
        sku_codes: Sequence[str],
    ) -> Sequence[PriceInfo]:
        try:
            response_skus = PriceFetcher._request_price_infos(sku_codes).json(
                parse_float=decimal.Decimal
            )["skus"]
            logger.debug(f"Received {len(response_skus)} price infos")
            return [PriceInfo(price_info) for price_info in response_skus]

        except _PriceQueryException as batch_query_exception:
            logger.warn(
                f"Price info query failed with status {batch_query_exception.request_status_code}"
            )
            if batch_query_exception.request_status_code == 400 and len(sku_codes) > 1:
                # Some SKUs are retired and probing their price will cause the server
                # to return an "internal error" if they are part as part of the
                # requested batch. In those cases, fallback to requesting the prices
                # one by one.
                logger.debug(
                    "Attempting to process failed price info query batch item by item"
                )
                price_infos = []
                for code in sku_codes:
                    try:
                        single_result = PriceFetcher._get_price_infos([code])
                        if single_result:
                            price_infos.append(single_result[0])
                        else:
                            logger.debug(
                                f"No price info returned for sku '{code}', skipping"
                            )
                    except _PriceQueryException as single_query_exception:
                        logger.warning(
                            f"Individual price info query failed with status {single_query_exception.request_status_code}"
                        )
                        if single_query_exception.request_status_code == 400:
                            logger.debug(f"Skipping price info query for sku '{code}'")
                            continue
                        else:
                            raise single_query_exception

                return price_infos
            else:
                raise batch_query_exception

    def __iter__(self) -> Iterator[PriceInfo]:
        # The API limits requests to 50 products
        for batch in self._batches(self._sku_codes, 50):
            try:
                for price_info in self._get_price_infos(batch):
                    yield price_info
            except _PriceQueryException:
                pass
