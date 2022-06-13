import sys

from canadiantracker.storage import (
    InvalidDatabaseRevisionException,
    ProductRepository,
    get_product_repository_from_sqlite_file,
)


def get_product_repository_from_sqlite_file_check_version(
    path: str,
) -> ProductRepository:
    try:
        return get_product_repository_from_sqlite_file(path)
    except InvalidDatabaseRevisionException as e:
        print(e)
        print()
        print("Make sure the database is at the latest revision.")
        sys.exit(1)
