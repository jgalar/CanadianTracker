import requests
import logging
from collections.abc import Sequence

logger = logging.getLogger(__name__)


class ProductListingEntry:
    def __init__(self, code: str, name: str, clearance: bool):
        self._code = code
        self._name = name
        self._clearance = clearance

    def __str__(self) -> str:
        return "[{code}] {name}".format(code=self._code, name=self._name)

    @property
    def name(self):
        return self._name

    @property
    def code(self):
        return self._code

    @property
    def is_in_clearance(self):
        return self._clearance

    def __repr__(self):
        props = {
            "name": self.name,
            "code": self.code,
            "is_in_clearance": self.is_in_clearance,
        }
        return str(props)


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
            "User-Agent": "HTTPie/2.6.0",
        }

        total_product_count = None
        enumerated_product_count = 0
        page = 1

        while (
            total_product_count is None
            or enumerated_product_count < total_product_count
        ):
            response = requests.get(url, headers=headers, params={"page": page})
            logger.debug("Fetching listing of page {}".format(page))
            page = page + 1

            if total_product_count is None:
                total_product_count = int(response.json()["totalResults"])
                logger.info("{} products to list".format(total_product_count))

            for product in response.json()["products"]:
                logger.debug("Product listing entry: " + str(product))
                enumerated_product_count = enumerated_product_count + 1
                yield ProductListingEntry(
                    product["code"], product["name"], product["clearance"] == "T"
                )


class ProductInfo:
    def __init__(self, result):
        # Keep the raw result so we can extract more information later.
        self._raw_payload = result

    @property
    def price(self) -> float:
        return float(self._raw_payload["Price"])

    @property
    def sku(self) -> str:
        return self._raw_payload["SKU"]

    @property
    def code(self) -> str:
        return self._raw_payload["Product"]

    @property
    def quantity(self) -> int:
        return self._raw_payload["Quantity"]

    @property
    def description(self) -> str:
        return self._raw_payload["Description"]

    @property
    def raw_payload(self) -> str:
        return str(self._raw_payload)

    def __repr__(self) -> str:
        return str(self.__dict__)


def get_product_infos(
    productListings: Sequence[ProductListingEntry],
) -> Sequence[ProductInfo]:
    url = "https://api-triangle.canadiantire.ca/esb/PriceAvailability"
    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Host": "api-triangle.canadiantire.ca",
        "User-Agent": "HTTPie/2.6.0",
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
