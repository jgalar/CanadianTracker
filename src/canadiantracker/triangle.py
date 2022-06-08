import requests
import logging
import fake_useragent
from collections.abc import Sequence, Iterable, Iterator

from canadiantracker.model import ProductListingEntry, ProductInfo

logger = logging.getLogger(__name__)


class _ProductCategory:
    def __init__(self, name: str, pretty_name: str):
        self._name = name
        self._pretty_name = pretty_name
        self._num_levels = len(name.split("::"))

    @property
    def name(self) -> str:
        return self._name

    @property
    def pretty_name(self) -> str:
        return self._pretty_name

    @property
    def num_levels(self) -> int:
        """Number of levels in the category."""
        return self._num_levels


class ProductInventory(Iterable):
    def __init__(
        self, dev_max_categories: int = 0, dev_max_pages_per_category: int = 0
    ):
        self._dev_max_pages_per_category = dev_max_pages_per_category
        response = ProductInventory._request_page().json()
        self._total_unique_products = int(response["query"]["total-results"])
        logger.debug(
            "API returned %i unique products to list", self._total_unique_products
        )
        self._total_products_to_list = 0

        self._product_categories = []
        for name, pretty_name in response["metadata"]["categoryMap"].items():
            # The Triangle product listing API seems to have an internal limit
            # that prevents listing more than ~10,000 items. To work around this,
            # we list products by category.
            #
            # Categories are hierarchical, for example: automotive,
            # automotive::car-cleaning. Overall, most products seem to belong to
            # a sub-category and to the higher-level categories that contain that
            # category.
            #
            # However, it seems some products can belong to the top-level
            # category exclusively. When that top-level category contains more
            # than ~10,000 items, we risk not being able to list some products
            # at all (albeit very few).
            #
            # Limiting ourselves to level 1 and 2 categories appears to allow
            # us to list most products while also limiting the number of products
            # re-listed for nothing.
            cat = _ProductCategory(name, pretty_name)
            if cat.num_levels == 1 or cat.num_levels == 2:
                self._product_categories.append(cat)

                if (
                    dev_max_categories != 0
                    and len(self._product_categories) == dev_max_categories
                ):
                    break

        # This takes a fair amount of time (1 request per category) just to have
        # an accurate number of items fed to the progress bar...
        #
        # In the grand scheme of things it doesn't matter much, but this
        # should probably be made optional.
        self._product_categories.sort(key=lambda category: category.name)
        for c in self._product_categories:
            response = ProductInventory._request_page(c).json()
            count = int(response["query"]["total-results"])
            logger.debug(
                "Product category %s (%s): %i products", c.name, c.pretty_name, count
            )
            self._total_products_to_list = self._total_products_to_list + count

        logger.debug(
            "%i products will be listed (with duplicates)", self._total_products_to_list
        )

    @staticmethod
    def _request_page(category: _ProductCategory = None, page_number: int = 1) -> dict:
        url = "https://api.canadiantire.ca/search/api/v0/product/en/"
        headers = {
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Host": "api.canadiantire.ca",
        }

        params = {"site": "ct", "page": page_number, "format": "json"}

        if category:
            params["x1"] = f"ast-id-level-{category.num_levels}"
            params["q1"] = category.name

        return requests.get(
            url,
            headers=headers,
            params=params,
        )

    # Name of the category currently being iterated on.
    @property
    def current_iteration_category_name(self) -> str:
        return self._currentCategory.pretty_name if self._currentCategory else None

    def __len__(self) -> int:
        return self._total_products_to_list

    def __iter__(self) -> Iterator[ProductListingEntry]:
        logger.debug("Starting enumaration of %i products", len(self))

        for category in self._product_categories:
            page = 1

            iterated_in_category = 0
            to_iterate_in_category = None
            self._currentCategory = category

            while (
                to_iterate_in_category is None
                or iterated_in_category < to_iterate_in_category
            ):
                response = ProductInventory._request_page(
                    category, page_number=page
                ).json()

                if to_iterate_in_category is None:
                    to_iterate_in_category = int(response["query"]["total-results"])

                logger.debug(
                    "Fetching listing of category {} (page {}, {}/{})".format(
                        category.pretty_name,
                        page,
                        iterated_in_category,
                        to_iterate_in_category,
                    )
                )

                for product in response["results"]:
                    iterated_in_category = iterated_in_category + 1
                    yield ProductListingEntry(
                        product["field"]["prod-id"],
                        product["field"]["prod-name"],
                        product["field"]["clearance"] == "T",
                        product["field"]["pdp-url"],
                    )

                if (
                    self._dev_max_pages_per_category != 0
                    and self._dev_max_pages_per_category == page
                ):
                    break

                page = page + 1


class ProductLedger(Iterable):
    def __init__(self, products: Iterator[ProductListingEntry]):
        self._products = products
        pass

    def __len__(self) -> int:
        return len(self._products)

    @staticmethod
    def _batches(it: Iterator, batch_max_size: int):
        batch = []
        for element in it:
            batch.append(element)
            if len(batch) == batch_max_size:
                yield batch
                batch = []

        if len(batch) > 0:
            yield batch

    @staticmethod
    def _user_agent() -> str:
        return fake_useragent.UserAgent().random

    @staticmethod
    def _get_product_infos(
        productListings: Sequence[ProductListingEntry],
    ) -> Sequence[ProductInfo]:
        url = "https://api-triangle.canadiantire.ca/esb/PriceAvailability"
        headers = {
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Host": "api-triangle.canadiantire.ca",
            "User-Agent": ProductLedger._user_agent(),
        }

        params = {
            "Product": ",".join([product.code for product in productListings]),
            "Banner": "CTR",
            "Language": "E",
        }

        logger.debug("requested {} product infos".format(len(productListings)))
        response = requests.get(url, headers=headers, params=params)
        logger.debug("received {} product infos".format(len(response.json())))
        logger.debug(str(response.json()))
        return [ProductInfo(product_info) for product_info in response.json()]

    def __iter__(self) -> Iterator[ProductInfo]:
        # The API limits requests to 40 products
        for batch in self._batches(self._products, 40):
            for product_info in self._get_product_infos(batch):
                yield product_info
