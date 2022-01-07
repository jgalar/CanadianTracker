import requests
import logging
from collections.abc import Sequence

from requests.models import Response
from canadiantracker.model import ProductListingEntry, ProductInfo

logger = logging.getLogger(__name__)


class ProductInventory:
    def __init__(self):
        self._total_product_count = None
        pass

    def _request_page(self, page_number) -> dict:
        url = "https://api.canadiantire.ca/search/api/v0/product/en/"
        headers = {
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Host": "api.canadiantire.ca",
        }

        return requests.get(
            url,
            headers=headers,
            params={"site": "ct", "page": page_number, "format": "json"},
        )

    def __len__(self) -> int:
        if self._total_product_count is None:
            response = self._request_page(1)
            self._total_product_count = int(response.json()["query"]["total-results"])

        return self._total_product_count

    def __iter__(self) -> ProductListingEntry:
        logger.debug("Enumerating %i products", len(self))
        enumerated_product_count = 0
        page = 1

        while enumerated_product_count < len(self):
            logger.debug("Fetching listing of page {}".format(page))
            response = self._request_page(page)

            page = page + 1

            for product in response.json()["results"]:
                enumerated_product_count = enumerated_product_count + 1
                yield ProductListingEntry(
                    product["field"]["prod-id"],
                    product["field"]["prod-name"],
                    product["field"]["clearance"] == "T",
                )


def get_product_infos(
    productListings: Sequence[ProductListingEntry],
) -> Sequence[ProductInfo]:
    url = "https://api-triangle.canadiantire.ca/esb/PriceAvailability"
    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Host": "api-triangle.canadiantire.ca",
    }

    params = {
        "Product": ",".join([product.code for product in productListings]),
        "Store": "0064",
        "Banner": "CTR",
        "isKiosk": "FALSE",
        "Language": "E",
    }

    logger.debug("requested {} product infos".format(len(productListings)))
    response = requests.get(url, headers=headers, params=params)
    logger.debug("received {} product infos".format(len(response.json())))
    logger.debug(str(response.json()))
    return [ProductInfo(product_info) for product_info in response.json()]
