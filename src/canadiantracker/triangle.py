import requests
import logging
from collections.abc import Sequence
from canadiantracker.model import ProductListingEntry, ProductInfo

logger = logging.getLogger(__name__)


class ProductInventory:
    def __init__(self):
        pass

    def __iter__(self) -> ProductListingEntry:
        url = "https://api.canadiantire.ca/search/api/v0/product/en/"
        headers = {
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Host": "api.canadiantire.ca",
        }

        total_product_count = None
        enumerated_product_count = 0
        page = 1

        while (
            total_product_count is None
            or enumerated_product_count < total_product_count
        ):
            response = requests.get(
                url,
                headers=headers,
                params={"site": "ct", "page": page, "format": "json"},
            )
            logger.debug("Fetching listing of page {}".format(page))
            with open("/tmp/page-{}.json".format(page), "w") as f:
                f.write(str(response.content.decode("utf-8")))

            page = page + 1

            if total_product_count is None:
                total_product_count = int(response.json()["query"]["total-results"])
                logger.info("{} products to list".format(total_product_count))

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
