from __future__ import annotations
import datetime
import decimal
from typing import Iterable


class ProductInfo:
    def __init__(self, result: dict):
        # Keep the raw result so we can extract more information later.
        self._raw_payload = result

    @property
    def price(self) -> decimal.Decimal | None:
        current_price = self._raw_payload["currentPrice"]
        if current_price is None:
            return None

        value = current_price["value"]
        assert type(value) is decimal.Decimal
        return value

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


class ProductListingEntry:
    def __init__(
        self, code: str, name: str, is_in_clearance: bool, url: str, skus: list[Sku]
    ):
        self._code = code
        self._name = name
        self._is_in_clearance = is_in_clearance
        self._url = url
        self._skus = skus

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
    def skus(self) -> Iterable[Sku]:
        return self._skus

    def __repr__(self):
        props = {
            "name": self.name,
            "code": self.code,
            "is_in_clearance": self._is_in_clearance,
        }
        return str(props)


class Sku:
    def __init__(self, code: str, formatted_code: str):
        self._code = code
        self._formatted_code = formatted_code

    @property
    def code(self) -> str:
        return self._code

    @property
    def formatted_code(self) -> str:
        return self._formatted_code


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
