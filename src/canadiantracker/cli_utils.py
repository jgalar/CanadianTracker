import sys

from canadiantracker import storage


def get_product_repository_from_sqlite_file_check_version(
    path: str,
) -> storage.ProductRepository:
    try:
        return storage.get_product_repository_from_sqlite_file(path)
    except storage.InvalidDatabaseRevisionException as e:
        print(e)
        print()
        print("Make sure the database is at the latest revision.")
        sys.exit(1)
