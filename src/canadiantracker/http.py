import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import canadiantracker.storage
from canadiantracker.model import ProductInfo, ProductInfoSample, ProductListingEntry

app = FastAPI()
_db_path = os.environ["CTSERVER_SERVE_DB_PATH"]
_templates = Jinja2Templates(directory=os.path.dirname(__file__) + "/web/templates")
_repository = canadiantracker.storage.get_product_repository_from_sqlite_file(_db_path)


@app.get("/api/products")
async def api_products():
    ret = []

    for p in _repository.products:
        ret.append(
            {
                "name": p.name,
                "code": p.code,
            }
        )

    return ret


def serialize_product_info(info: ProductInfo):
    return {
        "price": info.price,
        "in_promo": info.in_promo,
    }


def serialize_product_info_sample(sample: ProductInfoSample):
    return {
        "sample_time": sample.sample_time,
        "product_info": serialize_product_info(sample),
    }


@app.get("/api/products/{product_id}/samples")
async def api_product_samples(product_id):
    samples = _repository.get_product_info_samples_by_code(product_id)
    return [serialize_product_info_sample(sample) for sample in samples]


@app.get("/", response_class=HTMLResponse)
async def products(request: Request):

    return _templates.TemplateResponse("index.html", {"request": request})


def sanitize_sku(listing: ProductListingEntry) -> str:
    if not listing.sku:
        return listing.code

    return listing.sku.split("|")[0]


@app.get("/products/{product_id}", response_class=HTMLResponse)
async def one_product(request: Request, product_id):
    listing = _repository.get_product_listing_by_code(product_id)

    listing.sku = sanitize_sku(listing)

    return _templates.TemplateResponse(
        "product.html", {"request": request, "listing": listing}
    )
