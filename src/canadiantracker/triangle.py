from __future__ import annotations

import decimal
import logging
import time
from collections.abc import Iterable, Iterator, Sequence
from datetime import datetime
from typing import Callable, Generator, Tuple

import fake_useragent
import requests

from canadiantracker import model

logger = logging.getLogger(__name__)


class _ProductCategory:
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
    "authority": "apim.canadiantire.ca",
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9",
    "bannerid": "CTR",
    "basesiteid": "CTR",
    "ocp-apim-subscription-key": "c01ef3612328420c9f5cd9277e815a0e",
    "origin": "https://www.canadiantire.ca",
    "referer": "https://www.canadiantire.ca/",
    "sec-ch-ua": '" Not A;Brand";v="99", "Chromium";v="102", "Google Chrome";v="102"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "service-client": "ctr/web",
    "service-version": "ctc-dev2",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Safari/537.36",
    "x-web-host": "www.canadiantire.ca",
    "cache-control": "no-cache",
    "pragma": "no-cache",
}


class ProductInventory(Iterable):
    def __init__(
        self,
        category_levels_to_scrape: list[int] = None,
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
        )

    def __iter__(self) -> Iterator[model.ProductListingEntry]:
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
                response = ProductInventory._request_page(cat, level, page_number=page)
                response = response.json()

                if num_pages is None:
                    num_pages = int(response["pagination"]["total"])

                for product in response["products"]:
                    assert product["type"] == "PRODUCT"

                    skus = []
                    for sku in product["skus"]:
                        code = sku["code"]
                        formatted_code = sku["formattedCode"]
                        skus.append(model.Sku(code, formatted_code))

                    code = product["code"]
                    url = product["url"]
                    name = product["title"]
                    is_in_clearance = "CLEARANCE" in product["badges"]
                    yield model.ProductListingEntry(
                        code, name, is_in_clearance, url, skus
                    )

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


class ProductLedger(Iterable):
    def __init__(self, skus: Iterator[model.Sku]):
        self._skus = skus
        pass

    def __len__(self) -> int:
        return len(self._skus)

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
    def _user_agent() -> str:
        return fake_useragent.UserAgent().random

    @staticmethod
    def _get_product_infos(
        skus: Sequence[model.Sku],
    ) -> Sequence[model.ProductInfo]:
        for ntry in range(5):
            url = "https://apim.canadiantire.ca/v1/product/api/v1/product/sku/PriceAvailability/?lang=en_CA&storeId=64"
            headers = _base_headers.copy()
            headers["user-agent"] = ProductLedger._user_agent()
            headers["content-type"] = "application/json"

            body = {
                "skus": [
                    {
                        "code": sku.code,
                        "lowStockThreshold": 0,
                    }
                    for sku in skus
                ]
            }

            logger.debug("requested {} product infos".format(len(skus)))
            response = requests.post(url, headers=headers, json=body)

            if response.status_code != 200:
                # Wait a bit before retrying, in case the admin is restarting the container.
                logger.error(f"Got status code {response.status_code} on try {ntry}")
                time.sleep(5)
                continue

            with open("/tmp/res", "w") as f:
                f.write(response.text)

            response = response.json(parse_float=decimal.Decimal)
            response_skus = response["skus"]
            logger.debug("received {} product infos".format(len(response_skus)))

            return [model.ProductInfo(product_info) for product_info in response_skus]

        raise RuntimeError("Failed to get product info")

    def __iter__(self) -> Iterator[model.ProductInfo]:
        # The API limits requests to 50 products
        for batch in self._batches(self._skus, 50):
            for product_info in self._get_product_infos(batch):
                yield product_info
