import os
import json

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from canadiantracker import storage, model

app = FastAPI()
app.mount(
    "/static",
    StaticFiles(directory=os.path.dirname(__file__) + "/web/dist"),
    name="static",
)

_db_path = os.environ["CTSERVER_SERVE_DB_PATH"]
_templates = Jinja2Templates(directory=os.path.dirname(__file__) + "/web/templates")
_repository = storage.get_product_repository_from_sqlite_file(_db_path)


# This request takes a few seconds to execute, causing some delay when
# accessing the products page.  Since the contents of the database never
# changes while we're running, cache the returned Response object.
cached_products_response = None


@app.get("/api/products")
async def api_products() -> Response:
    global cached_products_response

    if cached_products_response is None:
        products = []

        for p in _repository.products:
            products.append(
                {
                    "name": p.name,
                    "code": p.code,
                }
            )

        cached_products_response = Response(
            json.dumps(products), media_type="application/json"
        )

    return cached_products_response


def serialize_product_info(info: model.ProductInfo) -> dict:
    return {
        "price": info.price,
        "in_promo": info.in_promo,
    }


def serialize_product_info_sample(sample: model.ProductInfoSample) -> dict:
    return {
        "sample_time": sample.sample_time,
        "product_info": serialize_product_info(sample),
    }


def serialize_sku(sku: model.Sku) -> dict:
    return {"code": sku.code, "formatted_code": sku.formatted_code}


@app.get("/api/products/{product_code}")
async def api_product(product_code: str) -> dict:
    product = _repository.get_product_listing_by_code(product_code)

    return {"skus": [serialize_sku(sku) for sku in product.skus]}


@app.get("/api/skus/{sku_code}/samples")
async def api_skus_samples(sku_code: str) -> list[dict]:
    sku = _repository.get_sku_by_code(sku_code)
    return [serialize_product_info_sample(sample) for sample in sku.samples]


@app.get("/", response_class=HTMLResponse)
async def products(request: Request) -> Jinja2Templates.TemplateResponse:

    return _templates.TemplateResponse("index.html", {"request": request})


@app.get("/products/{product_code}", response_class=HTMLResponse)
async def one_product(
    request: Request, product_code: str
) -> Jinja2Templates.TemplateResponse:
    product = _repository.get_product_listing_by_code(product_code)
    return _templates.TemplateResponse(
        "product.html", {"request": request, "product": product}
    )


def make_sku_url(sku_code: str, product_url: str) -> str:
    """Derive the url for sku SKU_CODE, given that the url for the product
    is PRODUCT_URL."""
    if not product_url.endswith("p.html"):
        return None

    return product_url[0:-4] + sku_code + ".html"


@app.get("/skus/{sku_code}", response_class=HTMLResponse)
async def one_sku(request: Request, sku_code: str) -> Jinja2Templates.TemplateResponse:
    sku = _repository.get_sku_by_code(sku_code)
    assert sku
    product_url = sku.product.url
    if product_url:
        sku_url = make_sku_url(sku.code, product_url)
    else:
        sku_url = None
    return _templates.TemplateResponse(
        "sku.html", {"request": request, "sku": sku, "sku_url": sku_url}
    )
