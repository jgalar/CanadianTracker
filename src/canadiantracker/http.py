import json
import os
from pathlib import Path

import starlette.templating
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from canadiantracker import storage

app = FastAPI()

# Determine which frontend to use
_use_svelte = os.environ.get("CTSERVER_USE_SVELTE", "0") == "1"
_base_dir = Path(__file__).parent

if _use_svelte:
    # Serve Svelte SPA assets
    app.mount(
        "/assets",
        StaticFiles(directory=_base_dir / "web-svelte" / "dist" / "assets"),
        name="assets",
    )
else:
    # Serve legacy jQuery frontend
    app.mount(
        "/static",
        StaticFiles(directory=_base_dir / "web" / "dist"),
        name="static",
    )

_templates = Jinja2Templates(directory=_base_dir / "web" / "templates")
_repository: storage.ProductRepository | None = None


def _get_repository() -> storage.ProductRepository:
    global _repository
    if _repository is None:
        db_path = os.environ["CTSERVER_SERVE_DB_PATH"]
        _repository = storage.get_product_repository_from_sqlite_file(db_path)
    return _repository


# This request takes a few seconds to execute, causing some delay when
# accessing the products page.  Since the contents of the database never
# changes while we're running, cache the returned Response object.
cached_products_response = None


@app.get("/api/products")
async def api_products() -> Response:
    global cached_products_response

    if cached_products_response is None:
        products = []

        for p in _get_repository().products():
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


def serialize_product_info(info: storage._StorageProductSample) -> dict:
    return {
        "price": info.price,
        "in_promo": info.in_promo,
    }


def serialize_product_info_sample(sample: storage._StorageProductSample) -> dict:
    return {
        "sample_time": sample.sample_time,
        "product_info": serialize_product_info(sample),
    }


def serialize_sku(sku: storage._StorageSku) -> dict:
    return {"code": sku.code, "formatted_code": sku.formatted_code}


def compute_sku_stats_light(sku: storage._StorageSku) -> dict:
    """Compute price statistics for a SKU (with last 3 months of samples for sparklines)."""
    price_stats = sku.get_price_stats()
    if price_stats is None:
        return {
            "current": 0,
            "all_time_low": 0,
            "all_time_high": 0,
            "samples": [],
        }

    # Query only recent samples (last 3 months) for the sparkline
    recent_samples = sku.get_recent_samples(days=90).all()

    sample_data = [
        {"time": int(s.sample_time.timestamp()), "price": s.price_cents}
        for s in recent_samples
    ]

    return {
        "current": price_stats.current,
        "all_time_low": price_stats.all_time_low,
        "all_time_high": price_stats.all_time_high,
        "samples": sample_data,
    }


@app.get("/api/search")
async def api_search(q: str = "") -> list[dict]:
    """Search products/SKUs by name, code, or SKU."""
    max_search_results = 500

    query = q.strip()
    if not query:
        return []

    repo = _get_repository()
    search_pattern = f"%{query}%"

    products = (
        repo.products()
        .filter(
            storage._StorageProduct.name.ilike(search_pattern)
            | storage._StorageProduct.code.ilike(search_pattern)
        )
        .limit(max_search_results)
        .all()
    )

    results = []
    for product in products:
        for sku in product.skus:
            stats = compute_sku_stats_light(sku)
            if stats["current"] == 0:
                continue
            results.append(
                {
                    "product_name": product.name,
                    "product_code": product.code,
                    "sku_code": sku.code,
                    "sku_formatted_code": sku.formatted_code,
                    "stats": stats,
                }
            )
            if len(results) >= max_search_results:
                break
        if len(results) >= max_search_results:
            break

    # If we haven't found enough, also search by SKU code
    if len(results) < max_search_results:
        skus = (
            repo.skus.filter(
                storage._StorageSku.code.ilike(search_pattern)
                | storage._StorageSku.formatted_code.ilike(search_pattern)
            )
            .limit(max_search_results - len(results))
            .all()
        )

        seen_sku_codes = {r["sku_code"] for r in results}
        for sku in skus:
            if sku.code in seen_sku_codes:
                continue
            stats = compute_sku_stats_light(sku)
            if stats["current"] == 0:
                continue
            results.append(
                {
                    "product_name": sku.product.name,
                    "product_code": sku.product.code,
                    "sku_code": sku.code,
                    "sku_formatted_code": sku.formatted_code,
                    "stats": stats,
                }
            )

    return results


@app.get("/api/deals")
async def api_deals(limit: int = 20) -> list[dict]:
    """Get best deals - items currently at or near their all-time low."""
    return []


@app.get("/api/products/{product_code}")
async def api_product(product_code: str) -> dict:
    product = _get_repository().get_product_by_code(product_code)

    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    return {"skus": [serialize_sku(sku) for sku in product.skus]}


@app.get("/api/skus/{sku_code}")
async def api_sku(sku_code: str) -> dict:
    """Get SKU details including product name."""
    sku = _get_repository().get_sku_by_code(sku_code)

    if sku is None:
        raise HTTPException(status_code=404, detail="SKU not found")

    return {
        "code": sku.code,
        "formatted_code": sku.formatted_code,
        "product_name": sku.product.name,
        "product_code": sku.product.code,
    }


@app.get("/api/skus/{sku_code}/samples")
async def api_skus_samples(sku_code: str) -> list[dict]:
    sku = _get_repository().get_sku_by_code(sku_code)

    if sku is None:
        raise HTTPException(status_code=404, detail="SKU not found")

    return [serialize_product_info_sample(sample) for sample in sku.samples]


def _serve_svelte_index() -> FileResponse:
    """Serve the Svelte SPA index.html."""
    return FileResponse(_base_dir / "web-svelte" / "dist" / "index.html")


def make_sku_url(sku_code: str, product_url: str) -> str | None:
    """Derive the url for sku SKU_CODE, given that the url for the product
    is PRODUCT_URL."""
    if not product_url.endswith("p.html"):
        return None

    return product_url[0:-4] + sku_code + ".html"


@app.get("/", response_class=HTMLResponse, response_model=None)
async def index(request: Request):
    if _use_svelte:
        return _serve_svelte_index()
    return _templates.TemplateResponse("index.html", {"request": request})


@app.get("/products/{product_code}", response_class=HTMLResponse, response_model=None)
async def one_product(request: Request, product_code: str):
    if _use_svelte:
        return _serve_svelte_index()
    product = _get_repository().get_product_by_code(product_code)
    return _templates.TemplateResponse(
        "product.html", {"request": request, "product": product}
    )


@app.get("/skus/{sku_code}", response_class=HTMLResponse, response_model=None)
async def one_sku(request: Request, sku_code: str):
    if _use_svelte:
        return _serve_svelte_index()
    sku = _get_repository().get_sku_by_code(sku_code)
    if sku is None:
        raise HTTPException(status_code=404, detail="SKU not found")

    product_url = sku.product.url
    if product_url:
        sku_url = make_sku_url(sku.code, product_url)
    else:
        sku_url = None
    return _templates.TemplateResponse(
        "sku.html", {"request": request, "sku": sku, "sku_url": sku_url}
    )
