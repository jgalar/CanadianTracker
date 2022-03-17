from fastapi import FastAPI
import os
import canadiantracker.storage

app = FastAPI()
_db_path = os.environ["CTSCRAPER_HTTP_DB_PATH"]


@app.get("/api/products")
async def products():
    repository = canadiantracker.storage.get_product_repository_from_sqlite_file(
        _db_path, should_create=False
    )

    ret = []

    for p in repository.products:
        ret.append(
            {
                "name": p.name,
                "code": p.code,
            }
        )

    return ret
