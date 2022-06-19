import datetime


class ProductInfo:
    def __init__(self, result: dict):
        # Keep the raw result so we can extract more information later.
        self._raw_payload = result

    @property
    def price(self) -> float:
        try:
            price = self._raw_payload["Promo"]["Price"]
        except KeyError:
            price = self._raw_payload["Price"]
        return float(price)

    @property
    def code(self) -> str:
        return self._raw_payload["Product"]

    @property
    def in_promo(self) -> bool:
        return "Promo" in self._raw_payload

    @property
    def raw_payload(self) -> str:
        return str(self._raw_payload)

    def __repr__(self) -> str:
        return str(self.__dict__)


class ProductListingEntry:
    def __init__(self, code: str, name: str, is_in_clearance: bool, url: str, sku: str):
        self._code = code
        self._name = name
        self._is_in_clearance = is_in_clearance
        self._url = url
        self._sku = sku

    def __str__(self) -> str:
        return "[{code}] {name}".format(code=self._code, name=self._name)

    @property
    def name(self) -> str:
        return self._name

    @property
    def code(self) -> str:
        return self._code

    @property
    def is_in_clearance(self) -> bool:
        return self._is_in_clearance

    @property
    def url(self) -> str:
        return self._url

    @property
    def sku(self) -> str:
        return self._sku

    def __repr__(self):
        props = {
            "name": self.name,
            "code": self.code,
            "is_in_clearance": self._is_in_clearance,
        }
        return str(props)


class ProductInfoSample:
    def __init__(self, product_info: ProductInfo, sample_time: datetime.datetime):
        self._sample_time = sample_time
        self._product_info = product_info

    @property
    def sample_time(self) -> datetime.datetime:
        return self._sample_time

    @property
    def product_info(self) -> ProductInfo:
        return self._product_info
