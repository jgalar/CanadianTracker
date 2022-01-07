import requests
import logging
import fake_useragent
from collections.abc import Sequence, Iterable, Iterator

from canadiantracker.model import ProductInfoSample, ProductListingEntry, ProductInfo

logger = logging.getLogger(__name__)

class _ProductCategory:
    def __init__(self, name: str, pretty_name: str):
        self._name = name
        self._pretty_name = pretty_name

    @property
    def name(self) -> str:
        return self._name

    @property
    def pretty_name(self) -> str:
        return self._pretty_name

class ProductInventory(Iterable):
    def __init__(self):
        response = ProductInventory._request_page().json()
        self._total_product_count = int(response["query"]["total-results"])

        self._product_categories = []
        for name, pretty_name in response["metadata"]["categoryMap"].items():
            # Only keep top-level categories
            #if len(name.split('::')) == 1 or len(name.split('::')) == 2:
            self._product_categories.append(_ProductCategory(name, pretty_name))

        self._product_categories.sort(key=lambda category: category.name)
        for c in self._product_categories:
            response = ProductInventory._request_page(c.name).json()
            count = int(response["query"]["total-results"])
            print(c.name + " : " + c.pretty_name + ": " + str(count) + " items")
        import sys
        sys.exit()

    @staticmethod
    def _request_page(category=None, page_number=1) -> dict:
        url = "https://api.canadiantire.ca/search/api/v0/product/en/"
        headers = {
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Host": "api.canadiantire.ca",
        }

        params = {"site": "ct", "page": page_number, "format": "json"}

        if category:
            params["x1"] = "ast-id-level-1"
            params["q1"] = category

        return requests.get(
            url,
            headers=headers,
            params=params,
        )

    def __len__(self) -> int:
        return self._total_product_count

    def __iter__(self) -> Iterator[ProductListingEntry]:
        logger.debug("Enumerating %i products", len(self))
        enumerated_product_count = 0
        page = 1

        while enumerated_product_count < len(self):
            logger.debug("Fetching listing of page {}".format(page))
            response = ProductInventory._request_page(page_number=page)

            with open('/tmp/response', 'w') as f:
                f.write(response.text)

            page = page + 1

            for product in response.json()["results"]:
                enumerated_product_count = enumerated_product_count + 1
                yield ProductListingEntry(
                    product["field"]["prod-id"],
                    product["field"]["prod-name"],
                    product["field"]["clearance"] == "T",
                )

class ProductLedger(Iterable):
    def __init__(self, products: Iterator[ProductListingEntry]):
        self._products = products
        pass

    def __len__(self) -> int:
        return len(self._products)

    @staticmethod
    def _batches(it: Iterator, batch_max_size: int):
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
        productListings: Sequence[ProductListingEntry],
    ) -> Sequence[ProductInfo]:
        url = "https://api-triangle.canadiantire.ca/esb/PriceAvailability"
        headers = {
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Host": "api-triangle.canadiantire.ca",
            "User-Agent": ProductLedger._user_agent()
        }

        params = {
            "Product": ",".join([product.code for product in productListings]),
            "Banner": "CTR",
            "Language": "E",
        }

        logger.debug("requested {} product infos".format(len(productListings)))
        response = requests.get(url, headers=headers, params=params)
        logger.debug("received {} product infos".format(len(response.json())))
        logger.debug(str(response.json()))
        return [ProductInfo(product_info) for product_info in response.json()]

    def __iter__(self) -> Iterator[ProductInfo]:
        # The API limits requests to 40 products
        for batch in self._batches(self._products, 40):
            for product_info in self._get_product_infos(batch):
                yield product_info
