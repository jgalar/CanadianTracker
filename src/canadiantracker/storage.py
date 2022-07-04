from __future__ import annotations
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

    def __init__(self, name: str, code: str, is_in_clearance: bool, url: str):
        self.name = name
        self.code = code
        self.is_in_clearance = is_in_clearance
        self.last_listed = datetime.datetime.now()
        self.url = url


class _StorageSku(sqlalchemy_base):
    # skus table
    __tablename__ = "skus"

    index = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    code = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    formatted_code = sqlalchemy.Column(sqlalchemy.String)
    product_index = sqlalchemy.Column(
        sqlalchemy.Integer, sqlalchemy.ForeignKey("products_static.index")
    )

    product = sqlalchemy.orm.relationship(
        "_StorageProductListingEntry", back_populates="skus"
    )

    def __init__(
        self,
        code: str,
        formatted_code: str,
        product: _StorageProductListingEntry,
    ):
        self.code = code
        self.formatted_code = formatted_code
        self.product = product


_StorageProductListingEntry.skus = sqlalchemy.orm.relationship(
    "_StorageSku", back_populates="product"
)


class _StorageProductSample(sqlalchemy_base):
    # sample of dynamic product properties
    __tablename__ = "samples"

    index = sqlalchemy.Column(
        sqlalchemy.Integer, primary_key=True, unique=True, index=True
    )
    sample_time = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False)
    sku_index = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("skus.index"),
        nullable=False,
        index=True,
    )
    price = sqlalchemy.Column(sqlalchemy.Numeric, nullable=False)
    in_promo = sqlalchemy.Column(sqlalchemy.Boolean, nullable=False)
    raw_payload = sqlalchemy.Column(sqlalchemy.String, nullable=True)

    sku = sqlalchemy.orm.relationship("_StorageSku", back_populates="samples")

    def __init__(
        self,
        price: float,
        in_promo: bool,
        raw_payload: dict,
        sku: _StorageSku,
    ):
        self.price = price
        self.in_promo = in_promo
        self.raw_payload = str(raw_payload)
        self.sample_time = datetime.datetime.now()
        self.sku = sku


_StorageSku.samples = sqlalchemy.orm.relationship(
    "_StorageProductSample", back_populates="sku"
)


class ProductRepository:
    def __init__(self):
        # Use a factory method to get an instance.
        raise NotImplementedError

    @property
    def products(self) -> Iterator[canadiantracker.model.ProductListingEntry]:
        raise NotImplementedError

    @property
    def skus(self) -> Iterator[canadiantracker.model.Sku]:
        raise NotImplementedError

    def get_product_listing_by_code(
        self, product_id: str
    ) -> canadiantracker.model.ProductListingEntry:
        raise NotImplementedError

    def get_sku_by_code(self, sku_code: str) -> canadiantracker.model.Sku:
        raise NotImplementedError

    def get_sku_by_formatted_code(
        self, sku_formatted_code: str
    ) -> canadiantracker.model.Sku:
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
    ALEMBIC_REVISION = "9169a7c5bda3"

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

    @property
    def skus(self) -> Iterator[canadiantracker.model.Sku]:
        return self._session.query(_StorageSku)

    def get_product_listing_by_code(
        self, product_id: str
    ) -> canadiantracker.model.ProductListingEntry:
        result = self.products.filter(_StorageProductListingEntry.code == product_id)
        return result.first() if result else None

    def get_sku_by_code(self, code: str) -> _StorageSku:
        result = self.skus.filter(_StorageSku.code == code)
        return result.first() if result else None

    def get_sku_by_formatted_code(
        self, sku_formatted_code: str
    ) -> canadiantracker.model.Sku:
        result = self.skus.filter(_StorageSku.formatted_code == sku_formatted_code)
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
        entry = (
            self._session.query(_StorageProductListingEntry)
            .filter_by(code=product_listing_entry.code)
            .first()
        )
        logger.debug("Product %s present in storage", "is" if entry else "is not")

        if not entry:
            entry = _StorageProductListingEntry(
                product_listing_entry.name,
                product_listing_entry.code.upper(),
                product_listing_entry.is_in_clearance,
                product_listing_entry.url,
            )
            add_entry = True
        else:
            add_entry = False

            # update last listed time
            setattr(entry, "last_listed", datetime.datetime.now())

            # If the URL is NULL, set it.
            if entry.url is None:
                logger.debug("Updating URL of existing product")
                entry.url = product_listing_entry.url

        # Get existing SKU codes for that products, to determine which SKUs
        # are new.
        existing_sku_codes = set()
        for sku in entry.skus:
            existing_sku_codes.add(sku.code)

        for sku in product_listing_entry.skus:
            if sku.code in existing_sku_codes:
                logger.debug(f"  SKU {sku.code} already present in storage")
                continue

            logger.debug(f"  SKU {sku.code} not present in storage, adding")
            _StorageSku(sku.code, sku.formatted_code, entry)

        if add_entry:
            self._session.add(entry)

    def add_product_price_samples(
        self, product_infos: Iterator[canadiantracker.model.ProductInfo]
    ) -> None:
        for info in product_infos:
            # Some responses have null as the current proce.
            price = info.price
            if price is None:
                continue

            sku = self.get_sku_by_code(info.code)
            assert sku

            new_sample = _StorageProductSample(
                price=price,
                in_promo=info.in_promo,
                raw_payload=info.raw_payload,
                sku=sku,
            )
            self._session.add(new_sample)


def get_product_repository_from_sqlite_file(path: str) -> ProductRepository:
    return _SQLite3ProductRepository(path)
