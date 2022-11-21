import os
import os.path

import pytest
import sqlalchemy

import alembic.config
import alembic.context
import alembic.environment
import alembic.migration
import alembic.script
from canadiantracker import model, storage


# Create a database in a temporary directory and initialize it with the
# expected schema.  Return a repository object using that database.
@pytest.fixture
def repository(tmp_path: str) -> storage._SQLite3ProductRepository:
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
        rev_scripts = reversed(
            list(
                mc.script.iterate_revisions(
                    lower="base",
                    upper=storage._SQLite3ProductRepository.ALEMBIC_REVISION,
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
        destination_rev=storage._SQLite3ProductRepository.ALEMBIC_REVISION,
    ) as ec:
        ec.configure(connection=conn)
        ec.run_migrations()

    return storage._SQLite3ProductRepository(sqlite_db_path)


def test_add_product(repository: storage._SQLite3ProductRepository):
    repository.add_product_listing_entry(
        model.ProductListingEntry("1234567", "Hello", False, "/foo", [])
    )
    products = list(repository.products)
    assert len(products) == 1
    p = products[0]
    assert p.code == "1234567"
    assert not p.is_in_clearance
    assert p.name == "Hello"
    assert p.url == "/foo"
    assert len(list(p.skus)) == 0
