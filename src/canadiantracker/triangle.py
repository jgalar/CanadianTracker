from __future__ import annotations

import asyncio
import decimal
import logging
import random
import shutil
import time
from collections.abc import Iterable, Iterator, Sequence
from datetime import datetime
from typing import Callable, Generator, Literal, Optional, Tuple

from camoufox.sync_api import Camoufox
from curl_cffi.requests import AsyncSession, Response

logger = logging.getLogger(__name__)


def _get_headless_mode() -> Literal["virtual"] | bool:
    """
    Determine the best headless mode for the current environment.

    Returns "virtual" if Xvfb is available (uses virtual display, more stealthy),
    otherwise returns True for pure headless mode (works everywhere but more detectable).
    """
    if shutil.which("Xvfb"):
        return "virtual"
    else:
        logger.warning(
            "Xvfb not found - using pure headless mode (more detectable). "
            "Install Xvfb for better stealth: apt install xvfb"
        )
        return True


# Domain used for cookie harvesting and API requests
_CT_DOMAIN = ".canadiantire.ca"
_CT_URL = "https://www.canadiantire.ca/"

# Time to wait for Akamai JS to set cookies (in milliseconds)
_COOKIE_HARVEST_WAIT_MS = 5000

# Session lifetime bounds (in seconds) - sessions expire randomly within this range
_SESSION_LIFETIME_MIN = 30 * 60  # 30 minutes
_SESSION_LIFETIME_MAX = 60 * 60  # 60 minutes

# Browser impersonation targets for curl_cffi (chosen once per session)
_IMPERSONATE_TARGETS = [
    "chrome133",
    "chrome136",
    "edge131",
    "safari18_0",
]


def _random_impersonate() -> str:
    """Return a random browser impersonation target."""
    return random.choice(_IMPERSONATE_TARGETS)


def _harvest_akamai_cookies() -> dict[str, str]:
    """
    Harvest Akamai cookies (_abck, bm_sz) by loading the site in a real browser.

    Uses Camoufox (a stealthy Firefox build) to load the Canadian Tire homepage,
    allowing Akamai's JavaScript to run and set the authentication cookies.

    Returns a dict of cookie name -> value for relevant Akamai cookies.
    """
    logger.info("Harvesting Akamai cookies using Camoufox...")
    cookies: dict[str, str] = {}

    try:
        # Use virtual display if Xvfb available, otherwise pure headless
        headless_mode = _get_headless_mode()
        with Camoufox(headless=headless_mode) as browser:
            page = browser.new_page()
            page.goto(_CT_URL)

            # Wait for Akamai JS to execute and set cookies
            page.wait_for_timeout(_COOKIE_HARVEST_WAIT_MS)

            # Extract all cookies
            for cookie in page.context.cookies():
                # We want _abck and bm_sz (both used by Akamai)
                if cookie["name"] in ("_abck", "bm_sz"):
                    cookies[cookie["name"]] = cookie["value"]
                    logger.debug(f"Harvested cookie: {cookie['name']}")

            page.close()

    except Exception as e:
        logger.warning(f"Failed to harvest Akamai cookies: {e}")

    if "_abck" in cookies:
        logger.info("Successfully harvested Akamai _abck cookie")
    else:
        logger.warning("Failed to harvest _abck cookie - requests may be blocked")

    return cookies


class Session:
    """
    Manages a persistent HTTP session using curl_cffi.

    Keeps the session and event loop alive between requests for better
    performance and to behave more like a real browser. The browser
    impersonation target is chosen randomly at session creation and
    remains consistent for all requests in the session.

    On session creation, Akamai cookies are harvested using a real browser
    (Camoufox) to help bypass bot detection.

    Sessions have a limited lifetime (30-60 minutes, randomly chosen) after
    which they are automatically destroyed and recreated. This mimics natural
    browsing behavior and prevents long-lived sessions that might be flagged.
    """

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._session: AsyncSession | None = None
        self._impersonate: str | None = None
        self._expires_at: float = 0  # Monotonic clock time when session expires

    def _is_expired(self) -> bool:
        """Check if the current session has exceeded its lifetime."""
        return time.monotonic() >= self._expires_at

    def _ensure_session(self) -> tuple[asyncio.AbstractEventLoop, AsyncSession, str]:
        """Ensure we have an active, non-expired event loop and session."""
        # Check if we need a new session (none exists, closed, or expired)
        need_new_session = (
            self._loop is None or self._loop.is_closed() or self._is_expired()
        )

        if need_new_session:
            # Close existing session if it's expired
            if self._loop is not None and not self._loop.is_closed():
                logger.info("Session expired, creating new session")
                self.close()

            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            session = AsyncSession()
            self._session = session
            # Choose impersonation target once per session for consistency
            self._impersonate = _random_impersonate()

            # Set random session lifetime
            lifetime = random.uniform(_SESSION_LIFETIME_MIN, _SESSION_LIFETIME_MAX)
            self._expires_at = time.monotonic() + lifetime
            logger.debug(
                f"Created new session with impersonate={self._impersonate}, "
                f"expires in {lifetime / 60:.1f} minutes"
            )

            # Harvest Akamai cookies and apply them to the session
            akamai_cookies = _harvest_akamai_cookies()
            for name, value in akamai_cookies.items():
                session.cookies.set(name, value, domain=_CT_DOMAIN)

        return self._loop, self._session, self._impersonate  # type: ignore[return-value]

    def get(self, url: str, **kwargs: object) -> Response:
        """Perform a GET request using the persistent session."""
        loop, session, impersonate = self._ensure_session()
        return loop.run_until_complete(
            session.get(url, impersonate=impersonate, **kwargs)
        )

    def post(self, url: str, **kwargs: object) -> Response:
        """Perform a POST request using the persistent session."""
        loop, session, impersonate = self._ensure_session()
        return loop.run_until_complete(
            session.post(url, impersonate=impersonate, **kwargs)
        )

    def close(self) -> None:
        """Close the session and event loop."""
        if self._session is not None:
            if self._loop is not None and not self._loop.is_closed():
                self._loop.run_until_complete(self._session.close())
            self._session = None
        if self._loop is not None and not self._loop.is_closed():
            self._loop.close()
            self._loop = None

    def __enter__(self) -> "Session":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


# Global shared session instance
_shared_session: Session | None = None


def _get_session() -> Session:
    """Get or create the shared session instance."""
    global _shared_session
    if _shared_session is None:
        _shared_session = Session()
    return _shared_session


class _ProductCategory:
    """A category in the store's product hierarchy."""

    def __init__(self, id: str, name: str, subcategories: list[_ProductCategory]):
        self._id = id
        self._name = name
        self._subcategories = subcategories
        self._parent = None

        for sub in self._subcategories:
            sub._parent = self

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def full_name(self) -> str:
        if self._parent:
            return f"{self._parent.full_name} > {self.name}"
        else:
            return self.name

    @property
    def subcategories(self) -> list[_ProductCategory]:
        return self._subcategories

    def visit(self, callback: Callable[[_ProductCategory, int], None], level: int):
        callback(self, level)
        for sub in self.subcategories:
            sub.visit(callback, level + 1)

    def iter_preorder(
        self, level: int
    ) -> Generator[Tuple[_ProductCategory, int], None, None]:
        yield self, level
        for cat in self.subcategories:
            yield from cat.iter_preorder(level + 1)


class _ProductCategories:
    """Collection of product categories forming a tree structure."""

    def __init__(self, categories: list[_ProductCategory]):
        self._categories = categories

    def visit(self, callback: Callable[[_ProductCategory, int], None]):
        for sub in self._categories:
            sub.visit(callback, 1)

    def iter_preorder(self):
        """Iterate on the category tree, in pre-order."""
        for cat in self._categories:
            yield from cat.iter_preorder(1)

    @property
    def categories(self) -> Iterable[_ProductCategory]:
        return self._categories


# Random delay range between requests (in seconds) to avoid rate limiting
_REQUEST_DELAY_MIN = 1.0
_REQUEST_DELAY_MAX = 3.0

# Exponential backoff settings for retries
_BACKOFF_BASE = 5.0  # Base delay in seconds
_BACKOFF_MAX = 60.0  # Maximum delay in seconds

# Batch size range for price queries (API limit is 50)
_BATCH_SIZE_MIN = 35
_BATCH_SIZE_MAX = 50


def _backoff_delay(attempt: int) -> float:
    """
    Calculate exponential backoff delay with jitter.

    Returns a delay that increases exponentially with each attempt,
    plus random jitter to avoid thundering herd.
    """
    delay = min(_BACKOFF_BASE * (2**attempt), _BACKOFF_MAX)
    # Add up to 25% jitter
    jitter = delay * random.uniform(0, 0.25)
    return delay + jitter


_base_headers = {
    "accept": "application/json, text/plain, */*",
    "bannerid": "CTR",
    "basesiteid": "CTR",
    "browse-mode": "OFF",
    "dnt": "1",
    "ocp-apim-subscription-key": "c01ef3612328420c9f5cd9277e815a0e",
    "referer": "https://www.canadiantire.ca/",
    "service-client": "ctr/web",
    "service-version": "v1",
    "x-web-host": "www.canadiantire.ca",
}


class Product:
    """A product returned by the Triangle API."""

    def __init__(self, code: str, name: str, is_in_clearance: bool, url: str):
        self._code = code
        self._name = name
        self._is_in_clearance = is_in_clearance
        self._url = url

    @property
    def code(self) -> str:
        return self._code

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_in_clearance(self) -> bool:
        return self._is_in_clearance

    @property
    def url(self) -> str:
        return self._url

    def __repr__(self):
        props = {
            "name": self.name,
            "code": self.code,
            "is_in_clearance": self._is_in_clearance,
        }
        return str(props)


class Sku:
    """A SKU returned by the Triangle API."""

    def __init__(self, code: str, formatted_code: str):
        self._code = code
        self._formatted_code = formatted_code

    @property
    def code(self) -> str:
        return self._code

    @property
    def formatted_code(self) -> str:
        return self._formatted_code

    def __repr__(self):
        props = {
            "code": self.code,
            "formatted_code": self.formatted_code,
        }
        return str(props)


class PriceInfo:
    """Price and availability info for a SKU returned by the Triangle API."""

    def __init__(self, result: dict):
        self._raw_payload = result

    @property
    def price(self) -> decimal.Decimal | None:
        current_price = self._raw_payload["currentPrice"]
        if current_price is None:
            return None

        value = current_price["value"]
        assert type(value) in [decimal.Decimal, int]
        return decimal.Decimal(value)

    @property
    def code(self) -> str:
        return self._raw_payload["code"]

    @property
    def in_promo(self) -> bool:
        return self._raw_payload["priceValidUntil"] is not None

    @property
    def raw_payload(self) -> str:
        return str(self._raw_payload)

    def __repr__(self) -> str:
        return str(self.__dict__)


class ProductInventory(Iterable):
    """Iterates over all products in the store's inventory via the Triangle API."""

    def __init__(
        self,
        category_levels_to_scrape: list[int] | None = None,
        dev_max_categories: int = 0,
        dev_max_pages_per_category: int = 0,
    ):
        self._dev_max_pages_per_category = dev_max_pages_per_category
        self._dev_max_categories = dev_max_categories
        # The Triangle product listing API seems to have an internal limit
        # that prevents listing more than ~10,000 items. To work around this,
        # we list products by category.
        #
        # Categories are hierarchical, for example: automotive,
        # automotive::car-cleaning. Overall, most products seem to belong to
        # a sub-category and to the higher-level categories that contain that
        # category.
        #
        # However, we have seen illogical results, where scraping, say, all level 2
        # categories under automotive, we found more products than by just scraping
        # automotive.  There is therefore some value in scraping all categories, at
        # all levels.  But it would be very expensive to do this every day.  There
        # are 5 levels of categories at the time of writing, so scraping all levels
        # would mean scraping 5 times the number of products.  To find a good
        # balance, the default is to scrape one category level, based on the number
        # of the day.  Note that this is only to discover new products, so at worst
        # it will take a few more days to discover a new product that only appears
        # in a specific category level, for some reason.
        self._categories = self._fetch_categories()
        max_level = 0
        for cat, level in self._categories.iter_preorder():
            logger.debug(f"[{level}] {cat.id} - {cat.full_name}")
            max_level = max(level, max_level)

        if category_levels_to_scrape is None:
            # No category level specified.  Choose one based on the current day.
            self._category_levels_to_scrape = [datetime.now().day % max_level + 1]
        else:
            self._category_levels_to_scrape = category_levels_to_scrape

        logger.debug(f"Category levels to scrape: {self._category_levels_to_scrape}")

    def _fetch_categories(self) -> _ProductCategories:
        """Fetch the list of categories, create some objects out of it."""
        response = _get_session().get(
            "https://apim.canadiantire.ca/v1/category/api/v1/categories",
            headers=_base_headers,
            params={"lang": "en_CA"},
        )

        if response.status_code != 200:
            logger.error(response.text)
            raise RuntimeError("Failed to get category list")

        def _handle_categories(raw: list[dict]) -> list[_ProductCategory]:
            def _handle_one_category(raw: dict) -> _ProductCategory:
                subcats = _handle_categories(raw["subcategories"])
                return _ProductCategory(raw["id"], raw["name"], subcats)

            cats = []
            for c in raw:
                cats.append(_handle_one_category(c))
            cats.sort(key=lambda category: category.name)
            return cats

        categories = _handle_categories(response.json()["categories"])
        return _ProductCategories(categories)

    @staticmethod
    def _request_page(
        cat: _ProductCategory, cat_level: int, page_number: int = 1
    ) -> Response:
        """Fetch one page of products."""
        return _get_session().get(
            f"https://apim.canadiantire.ca/v1/search/search?store=64&lang=en_CA&x1=ast-id-level-{cat_level}&q1={cat.id}&experience=category;count=48;page={page_number}",
            headers=_base_headers,
        )

    def __iter__(self) -> Iterator[Product]:
        num_categories_scraped = 0

        for cat, level in self._categories.iter_preorder():
            if level not in self._category_levels_to_scrape:
                continue

            num_categories_scraped += 1

            logger.debug(f"Starting category {cat.full_name}")
            page = 1
            num_pages = None

            while num_pages is None or page < (num_pages + 1):
                logger.debug(
                    f"Fetching listing of category {cat.full_name} (page {page}/{num_pages})"
                )
                try:
                    response = ProductInventory._request_page(
                        cat, level, page_number=page
                    )
                except Exception as e:
                    logger.warning(f"Page request failed with exception: {e}")
                    continue

                response = response.json()

                if num_pages is None:
                    num_pages = int(response["pagination"]["total"])

                for product in response["products"]:
                    assert product["type"] == "PRODUCT"

                    code = product["code"]
                    url = product["url"]
                    name = product["title"]
                    is_in_clearance = "CLEARANCE" in product["badges"]
                    yield Product(code, name, is_in_clearance, url)

                if (
                    self._dev_max_pages_per_category != 0
                    and self._dev_max_pages_per_category == page
                ):
                    break

                # Random delay between page requests to avoid rate limiting
                time.sleep(random.uniform(_REQUEST_DELAY_MIN, _REQUEST_DELAY_MAX))
                page = page + 1

            if (
                self._dev_max_categories != 0
                and self._dev_max_categories == num_categories_scraped
            ):
                break


class NoSuchProductException(RuntimeError):
    """Raised when a product does not exist in the Triangle API."""

    pass


class UnknownProductErrorException(RuntimeError):
    """Raised when an unknown error occurs while fetching a product."""

    pass


class SkusInventory(Iterable):
    """Fetches all SKUs for a given product from the Triangle API."""

    def __init__(self, product_code: str):
        self._product_code = product_code

    @staticmethod
    def _request_page(product_code: str) -> Response:
        """Fetch one product page."""
        headers = _base_headers.copy()
        return _get_session().get(
            f"https://apim.canadiantire.ca/v1/product/api/v1/product/productFamily/{product_code}?baseStoreId=CTR&lang=en_CA&storeId=64",
            headers=headers,
            timeout=10,
        )

    def __iter__(self):
        for ntry in range(5):
            resp = SkusInventory._request_page(self._product_code)
            if resp.status_code == 404:
                raise NoSuchProductException
            if resp.status_code not in (200, 206):
                delay = _backoff_delay(ntry)
                logger.error(
                    f"Got status code {resp.status_code} on try {ntry}, "
                    f"backing off for {delay:.1f}s"
                )
                time.sleep(delay)
                continue

            resp = resp.json()
            # Some stale products didn't have a skus list in the response.  The
            # CT website was broken for those, so we just ignore them.
            if "skus" not in resp or resp["skus"] is None:
                return

            for sku in resp["skus"]:
                yield Sku(sku["code"], sku["formattedCode"])

            # Random delay after successful request to avoid rate limiting
            time.sleep(random.uniform(_REQUEST_DELAY_MIN, _REQUEST_DELAY_MAX))
            return

        raise UnknownProductErrorException


class _PriceQueryException(Exception):
    """Raised on a non-200 HTTP response when querying prices."""

    def __init__(self, msg: str, request_status_code: Optional[int] = None):
        super().__init__(msg, request_status_code)
        self._request_status_code = request_status_code

    @property
    def request_status_code(self) -> Optional[int]:
        return self._request_status_code


class PriceFetcher(Iterable):
    """Fetches price info for SKUs in batches from the Triangle API."""

    def __init__(self, sku_codes: Iterator[str]):
        self._sku_codes = sku_codes

    @staticmethod
    def _batches(
        it: Iterator, batch_min_size: int, batch_max_size: int
    ) -> Generator[list, None, None]:
        """
        Yield batches of elements with randomized sizes.

        Each batch has a randomly chosen size between batch_min_size and
        batch_max_size to make request patterns less predictable.
        """
        batch = []
        # Choose a random target size for this batch
        target_size = random.randint(batch_min_size, batch_max_size)
        for element in it:
            batch.append(element)
            if len(batch) == target_size:
                yield batch
                batch = []
                # Choose a new random size for the next batch
                target_size = random.randint(batch_min_size, batch_max_size)

        if len(batch) > 0:
            yield batch

    @staticmethod
    def _request_price_infos(sku_codes: Sequence[str]) -> Response:
        for ntry in range(5):
            url = "https://apim.canadiantire.ca/v1/product/api/v1/product/sku/PriceAvailability/?lang=en_CA&storeId=64"
            headers = _base_headers.copy()
            headers["content-type"] = "application/json"

            body = {
                "skus": [
                    {
                        "code": sku_code,
                        "lowStockThreshold": 0,
                    }
                    for sku_code in sku_codes
                ]
            }

            logger.debug(
                f"Sending batched price info query request: ntry={ntry} batch_size={len(sku_codes)} sku_codes={sku_codes}"
            )
            try:
                response = _get_session().post(
                    url,
                    headers=headers,
                    json=body,
                    timeout=10,
                )
            except Exception as e:
                logger.warning(
                    f"Batched price info query request failed with exception: ntry={ntry} batch_size={len(sku_codes)} sku_codes={sku_codes}, exception={e}"
                )
                continue

            if response.status_code != 200:
                logger.error(f"Got status code {response.status_code} on try {ntry}")
                logger.error(response.text)

                if "Request failed with status code 404" in response.text:
                    raise _PriceQueryException("Failed to get product info", 404)
                elif response.status_code == 400:
                    raise _PriceQueryException(
                        "Failed to get product info", response.status_code
                    )

                # Exponential backoff before retrying
                delay = _backoff_delay(ntry)
                logger.debug(f"Backing off for {delay:.1f}s before retry")
                time.sleep(delay)
                continue

            return response

        raise _PriceQueryException("Failed to get product info")

    @staticmethod
    def _get_price_infos(
        sku_codes: Sequence[str],
    ) -> Sequence[PriceInfo]:
        try:
            response_skus = PriceFetcher._request_price_infos(sku_codes).json(
                parse_float=decimal.Decimal
            )["skus"]
            logger.debug(f"Received {len(response_skus)} price infos")
            return [PriceInfo(price_info) for price_info in response_skus]

        except _PriceQueryException as batch_query_exception:
            logger.warning(
                f"Price info query failed with status {batch_query_exception.request_status_code}"
            )
            if batch_query_exception.request_status_code == 400 and len(sku_codes) > 1:
                # Some SKUs are retired and probing their price will cause the server
                # to return an "internal error" if they are part as part of the
                # requested batch. In those cases, fallback to requesting the prices
                # one by one.
                logger.debug(
                    "Attempting to process failed price info query batch item by item"
                )
                price_infos = []
                for code in sku_codes:
                    try:
                        single_result = PriceFetcher._get_price_infos([code])
                        if single_result:
                            price_infos.append(single_result[0])
                        else:
                            logger.debug(
                                f"No price info returned for sku '{code}', skipping"
                            )
                    except _PriceQueryException as single_query_exception:
                        logger.warning(
                            f"Individual price info query failed with status {single_query_exception.request_status_code}"
                        )
                        if single_query_exception.request_status_code == 400:
                            logger.debug(f"Skipping price info query for sku '{code}'")
                            continue
                        else:
                            raise single_query_exception

                return price_infos
            else:
                raise batch_query_exception

    def __iter__(self) -> Iterator[PriceInfo]:
        # The API limits requests to 50 products; use variable batch sizes
        for batch in self._batches(self._sku_codes, _BATCH_SIZE_MIN, _BATCH_SIZE_MAX):
            try:
                for price_info in self._get_price_infos(batch):
                    yield price_info
            except _PriceQueryException:
                pass
            # Random delay between batch requests to avoid rate limiting
            time.sleep(random.uniform(_REQUEST_DELAY_MIN, _REQUEST_DELAY_MAX))
