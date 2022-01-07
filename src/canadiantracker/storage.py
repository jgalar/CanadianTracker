import sqlalchemy
import sqlalchemy.orm
import canadiantracker.model
import sys
import os
import datetime
from collections.abc import Iterator
import logging

logger = logging.getLogger(__name__)

sqlalchemy_base = sqlalchemy.orm.declarative_base()


class _StorageProductListingEntry(sqlalchemy_base):
    # static product properties
    __tablename__ = "products_static"

    index = sqlalchemy.Column(
        sqlalchemy.Integer, primary_key=True, unique=True, index=True
    )
    name = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    code = sqlalchemy.Column(sqlalchemy.String, unique=True, nullable=False)
    is_in_clearance = sqlalchemy.Column(sqlalchemy.Boolean)
    # last time this entry was returned when listing the inventory
    # this will be used to prune stale product entries
    last_listed = sqlalchemy.Column(sqlalchemy.DateTime)

    def __init__(self, name: str, code: str, is_in_clearance: bool):
        self.name = name
        self.code = code
        self.is_in_clearance = is_in_clearance
        self.last_listed = datetime.datetime.now()


class _StorageProductSample(sqlalchemy_base):
    # sample of dynamic product properties
    __tablename__ = "products_dynamic"

    index = sqlalchemy.Column(
        sqlalchemy.Integer, primary_key=True, unique=True, index=True
    )
    sample_time = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False)
    code = sqlalchemy.Column(
        sqlalchemy.String,
        sqlalchemy.ForeignKey("products_static.code"),
        nullable=False,
        index=True,
    )
    price = sqlalchemy.Column(sqlalchemy.Numeric, nullable=False)
    in_promo = sqlalchemy.Column(sqlalchemy.Boolean, nullable=False)
    raw_payload = sqlalchemy.Column(sqlalchemy.String, nullable=True)

    def __init__(self, code: str, price: float, in_promo: bool, raw_payload: dict):
        self.code = code
        self.price = price
        self.in_promo = in_promo
        self.raw_payload = str(raw_payload)
        self.sample_time = datetime.datetime.now()


class ProductRepository:
    def __init__(self):
        # Use a factory method to get an instance.
        raise NotImplementedError

    def add_product_listing_entry(
        self, product_listing_entry: canadiantracker.model.ProductListingEntry
    ) -> None:
        raise NotImplementedError

    def add_product_price_sample(
        self, product_price_sample: canadiantracker.model.ProductInfoSample
    ) -> None:
        raise NotImplementedError


class _SQLite3ProductRepository(ProductRepository):
    def __init__(self, path: str):
        db_url = "sqlite:///" + os.path.abspath(path)
        logger.debug("Creating SQLite3ProductRepository with url `%s`", db_url)
        self._engine = sqlalchemy.create_engine(db_url, echo=False)
        self._session = sqlalchemy.orm.sessionmaker(bind=self._engine)()
        sqlalchemy_base.metadata.create_all(self._engine)

    def __del__(self):
        self._session.commit()

    @property
    def products(self) -> Iterator[canadiantracker.model.ProductListingEntry]:
        return self._session.query(_StorageProductListingEntry)

    def add_product_listing_entry(
        self, product_listing_entry: canadiantracker.model.ProductListingEntry
    ) -> None:
        logger.debug(
            "Attempting to add product: code = `%s`", product_listing_entry.code
        )
        existing_entry = (
            self._session.query(_StorageProductListingEntry)
            .filter_by(code=product_listing_entry.code)
            .first()
        )
        logger.debug(
            "Product %s present in storage", "is" if existing_entry else "is not"
        )
        new_entry = _StorageProductListingEntry(
            product_listing_entry.name,
            product_listing_entry.code,
            product_listing_entry.is_in_clearance,
        )

        if not existing_entry:
            self._session.add(new_entry)
        else:
            # update last listed time
            setattr(existing_entry, "last_listed", datetime.datetime.now())

    def add_product_price_samples(
        self, product_infos: Iterator[canadiantracker.model.ProductInfo]
    ) -> None:
        for product in product_infos:
            new_sample = _StorageProductSample(
                code=product.code,
                price=product.price,
                in_promo=product.in_promo,
                raw_payload=product.raw_payload,
            )
            self._session.add(new_sample)


def get_product_repository_from_sqlite_file(
    path: str, should_create: bool
) -> ProductRepository:
    return _SQLite3ProductRepository(path)