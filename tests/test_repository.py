import os
import os.path

import pytest
import sqlalchemy

import alembic.config
import alembic.context
import alembic.environment
import alembic.migration
import alembic.script
from canadiantracker import storage


# Create a database in a temporary directory and initialize it with the
# expected schema.  Return a repository object using that database.
@pytest.fixture
def repository(tmp_path: str) -> storage.ProductRepository:
    sqlite_db_path = os.path.join(tmp_path, "inventory.db")
    engine = sqlalchemy.create_engine(f"sqlite:///{sqlite_db_path}")
    conn = engine.connect()
    config = alembic.config.Config()

    # This assumes that pytest is ran from the repository's root.  Not ideal,
    # but that's a start.
    config.set_main_option("script_location", os.path.join(os.getcwd(), "alembic"))
    script = alembic.script.ScriptDirectory.from_config(config)

    def do_upgrade(
        heads: tuple[str, ...] | tuple[()], mc: alembic.migration.MigrationContext
    ) -> list[alembic.migration.MigrationStep]:
        assert mc.script
        rev_scripts = reversed(
            list(
                mc.script.iterate_revisions(
                    lower="base",
                    upper=storage.ProductRepository.ALEMBIC_REVISION,
                )
            )
        )

        return [
            alembic.migration.MigrationStep.upgrade_from_script(
                mc.script.revision_map, x
            )
            for x in rev_scripts
        ]

    with alembic.environment.EnvironmentContext(
        config,
        script,
        fn=do_upgrade,
        destination_rev=storage.ProductRepository.ALEMBIC_REVISION,
    ) as ec:
        ec.configure(connection=conn)
        ec.run_migrations()

    return storage.ProductRepository(sqlite_db_path)


def test_add_product(repository: storage.ProductRepository):
    repository.add_product("1234567P", "Hello", False, "/foo")
    products = list(repository.products())
    assert len(products) == 1
    p = products[0]
    assert p.code == "1234567P"
    assert not p.is_in_clearance
    assert p.name == "Hello"
    assert p.url == "/foo"
    assert len(list(p.skus)) == 0


def test_add_product_wrong_code_format(repository: storage.ProductRepository):
    with pytest.raises(ValueError):
        repository.add_product("1234567", "Hello", False, "/foo")


def test_list_products_filter(repository: storage.ProductRepository):
    repository.add_product("1234567P", "Hello", False, "/foo")
    repository.add_product("2345678P", "Hello", False, "/foo")
    repository.add_product("3456789P", "Hello", False, "/foo")

    products = sorted(
        repository.products(["1234567P", "3456789P"]), key=lambda p: p.code
    )
    assert len(products) == 2
    assert products[0].code == "1234567P"
    assert products[1].code == "3456789P"


def test_list_products_filter_wrong_code_format(repository: storage.ProductRepository):
    with pytest.raises(ValueError):
        repository.products(["1234567p"])


def test_get_product_by_code(repository: storage.ProductRepository):
    repository.add_product("1234567P", "Hello", False, "/foo")

    product = repository.get_product_by_code("1234567P")
    assert product
    assert product.code == "1234567P"


def test_get_product_by_code_wrong_code_format(repository: storage.ProductRepository):
    with pytest.raises(ValueError):
        repository.get_product_by_code("1234567p")
