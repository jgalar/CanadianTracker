import sqlalchemy
import sqlalchemy.orm
import canadiantracker.model
import sys
import os
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
    last_listed = sqlalchemy.Column(sqlalchemy.Date)

    def __init__(self, name: str, code: str, is_in_clearance: bool):
        self.name = name
        self.code = code
        self.is_in_clearance = is_in_clearance


class ProductRepository:
    def __init__(self):
        # Use a factory method to get an instance.
        raise NotImplementedError

    def add_product_listing_entry(
        self, product_listing_entry: canadiantracker.model.ProductListingEntry
    ):
        raise NotImplementedError

    def add_product_price_sample(
        self, product_price_sample: canadiantracker.model.ProductInfoSample
    ):
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

    def add_product_listing_entry(
        self, product_listing_entry: canadiantracker.model.ProductListingEntry
    ):
        logger.debug(
            "Attempting to add product: code = `%s`", product_listing_entry.code
        )
        exists = (
            self._session.query(_StorageProductListingEntry)
            .filter_by(code=product_listing_entry.code)
            .first()
        )
        logger.debug("Product %s present in storage", "is" if exists else "is not")
        if not exists:
            entry = _StorageProductListingEntry(
                product_listing_entry.name,
                product_listing_entry.code,
                product_listing_entry.is_in_clearance,
            )
            self._session.add(entry)


def get_product_repository_from_sqlite_file(
    path: str, should_create: bool
) -> ProductRepository:
    return _SQLite3ProductRepository(path)
