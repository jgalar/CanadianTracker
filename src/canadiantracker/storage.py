import sqlalchemy
import sqlalchemy.orm
import canadiantracker.model
import os
import datetime
from collections.abc import Iterator
import logging

logger = logging.getLogger(__name__)

sqlalchemy_metadata = sqlalchemy.MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)

sqlalchemy_base = sqlalchemy.orm.declarative_base(metadata=sqlalchemy_metadata)


class _AlembicRevision(sqlalchemy_base):
    __tablename__ = "alembic_version"

    version_num = sqlalchemy.Column(sqlalchemy.String, primary_key=True)


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
    url = sqlalchemy.Column(sqlalchemy.String)
    sku = sqlalchemy.Column(sqlalchemy.String)

    def __init__(self, name: str, code: str, is_in_clearance: bool, url: str, sku: str):
        self.name = name
        self.code = code
        self.is_in_clearance = is_in_clearance
        self.last_listed = datetime.datetime.now()
        self.url = url
        self.sku = sku


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

    @property
    def products(self) -> Iterator[canadiantracker.model.ProductListingEntry]:
        raise NotImplementedError

    def get_product_listing_by_code(
        self, product_id: str
    ) -> canadiantracker.model.ProductListingEntry:
        raise NotImplementedError

    def get_product_info_samples_by_code(
        self, product_id: str
    ) -> Iterator[canadiantracker.model.ProductInfoSample]:
        raise NotImplementedError

    def add_product_listing_entry(
        self, product_listing_entry: canadiantracker.model.ProductListingEntry
    ) -> None:
        raise NotImplementedError

    def add_product_price_sample(
        self, product_price_sample: canadiantracker.model.ProductInfoSample
    ) -> None:
        raise NotImplementedError


class InvalidDatabaseRevisionException(Exception):
    def __init__(self, msg: str):
        self._msg = msg

    def __str__(self):
        return f"Failed to validate database revision: {self._msg}"


class _SQLite3ProductRepository(ProductRepository):
    ALEMBIC_REVISION = "4e2a96338a6c"

    def __init__(self, path: str):
        db_url = "sqlite:///" + os.path.abspath(path)
        logger.debug("Creating SQLite3ProductRepository with url `%s`", db_url)
        self._engine = sqlalchemy.create_engine(db_url, echo=False)
        inspector: sqlalchemy.engine.reflection.Inspector = sqlalchemy.inspect(
            self._engine
        )
        if not inspector.has_table("alembic_version"):
            raise InvalidDatabaseRevisionException(
                "database is missing the alembic_version table"
            )

        self._session: sqlalchemy.orm.Session = sqlalchemy.orm.sessionmaker(
            bind=self._engine
        )()

        revs: list[_AlembicRevision] = self._session.query(_AlembicRevision).all()

        if len(revs) == 0:
            raise InvalidDatabaseRevisionException("table alembic_revision is empty")

        rev = revs[0].version_num
        if rev != self.ALEMBIC_REVISION:
            raise InvalidDatabaseRevisionException(
                f"expected {self.ALEMBIC_REVISION}, got {rev}"
            )

    def __del__(self):
        if hasattr(self, "_session"):
            self._session.commit()

    @property
    def products(self) -> Iterator[canadiantracker.model.ProductListingEntry]:
        return self._session.query(_StorageProductListingEntry)

    def get_product_listing_by_code(
        self, product_id: str
    ) -> canadiantracker.model.ProductListingEntry:
        result = self.products.filter(_StorageProductListingEntry.code == product_id)
        return result.first() if result else None

    def get_product_info_samples_by_code(
        self, product_id: str
    ) -> Iterator[canadiantracker.model.ProductInfoSample]:
        result = (
            self._session.query(_StorageProductSample)
            .filter(_StorageProductSample.code == product_id)
            .order_by(_StorageProductSample.sample_time)
        )
        return result.all() if result else None

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
            product_listing_entry.code.upper(),
            product_listing_entry.is_in_clearance,
            product_listing_entry.url,
            product_listing_entry.sku,
        )

        if not existing_entry:
            self._session.add(new_entry)
        else:
            # update last listed time
            setattr(existing_entry, "last_listed", datetime.datetime.now())

            # If the URL is NULL, set it.
            if existing_entry.url is None:
                logger.debug("Updating URL of existing product")
                existing_entry.url = product_listing_entry.url

            # If the SKU is NULL, set it.
            if existing_entry.sku is None:
                logger.debug("Updating SKU of existing product")
                existing_entry.sku = product_listing_entry.sku

    def add_product_price_samples(
        self, product_infos: Iterator[canadiantracker.model.ProductInfo]
    ) -> None:
        for product in product_infos:
            new_sample = _StorageProductSample(
                code=product.code.upper(),
                price=product.price,
                in_promo=product.in_promo,
                raw_payload=product.raw_payload,
            )
            self._session.add(new_sample)


def get_product_repository_from_sqlite_file(path: str) -> ProductRepository:
    return _SQLite3ProductRepository(path)
