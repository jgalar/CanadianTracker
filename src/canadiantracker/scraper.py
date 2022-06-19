import click
import sys
import logging
import textwrap
from canadiantracker.cli_utils import (
    get_product_repository_from_sqlite_file_check_version,
)

import canadiantracker.triangle
import canadiantracker.storage
import canadiantracker.model


logger = logging.getLogger(__name__)


def print_welcome() -> None:
    click.echo(
        click.style(
            "Bienvenue chez Canadian Scraper",
            fg="green",
            bold=True,
        )
        + " / "
        + click.style(
            "Welcome to Canadian Scraper",
            fg="red",
            bold=True,
        )
    )


@click.group()
@click.option("-d", "--debug", is_flag=True, help="Set logging level to DEBUG")
def cli(debug: bool, args=None) -> None:
    """
    CanadianTracker tracks the inventory and prices of your favorite canadian
    retailer using the internal API that powers canadiantire.ca.

    \b
    Due to the design of the Canadian Tire API and its relatively poor
    performance, it does so in two steps implemented as two commands:
      - scrape-inventory:
        fetch static product properties (e.g. codes, description, etc.)
      - scrape-prices:
        fetch the current price of listed products

    Use --help on any of the commands for more information on their role and options.
    """
    print_welcome()
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO)


def progress_bar_product_name(
    product_listing_entry: canadiantracker.model.ProductListingEntry,
) -> str:
    return product_listing_entry.name


@cli.command(name="scrape-inventory", short_help="fetch static product properties")
@click.option(
    "--db-path",
    required=True,
    type=str,
    metavar="PATH",
    help="Path to sqlite db instance",
)
@click.option(
    "--dev-max-categories",
    default=0,
    help="Maximum number of categories to fetch (developer option)",
    metavar="NUM",
)
@click.option(
    "--dev-max-pages-per-category",
    default=0,
    help="Maximum number of pages to fetch per category (developer option)",
    metavar="NUM",
)
def scrape_inventory(
    db_path: str, dev_max_categories: int, dev_max_pages_per_category: int
) -> None:
    """
    Fetch static product properties.
    """

    repository = get_product_repository_from_sqlite_file_check_version(db_path)
    inventory = canadiantracker.triangle.ProductInventory(
        dev_max_categories=dev_max_categories,
        dev_max_pages_per_category=dev_max_pages_per_category,
    )

    progress_bar_settings = {
        "label": "Scraping inventory",
        "show_pos": True,
        "item_show_func": lambda p: textwrap.shorten(
            p.name, width=32, placeholder="..."
        )
        if p
        else None,
    }

    if logging.root.level == logging.DEBUG:
        # Deactivate progress bar in debug mode since its updates make the
        # output very spammy
        progress_bar_settings["bar_template"] = ""

    with click.progressbar(inventory, **progress_bar_settings) as bar_wrapper:
        for product_listing in bar_wrapper:
            repository.add_product_listing_entry(product_listing)


@cli.command(name="scrape-prices", short_help="fetch current product prices")
@click.option(
    "--db-path",
    required=True,
    type=str,
    metavar="PATH",
    help="Path to sqlite db instance",
)
@click.option(
    "--older-than",
    type=int,
    metavar="DAYS",
    default=1,
    show_default=True,
    help="Only scrape prices for products that were not updated in the last N days (ignored for the moment)",
)
def scrape_prices(db_path: str, older_than: int) -> None:
    """
    Fetch current product prices.
    """
    repository = get_product_repository_from_sqlite_file_check_version(db_path)

    progress_bar_settings = {
        "label": "Scraping prices",
        "show_pos": True,
        "item_show_func": lambda p: textwrap.shorten(
            p.name, width=32, placeholder="..."
        )
        if p
        else None,
    }

    if logging.root.level == logging.DEBUG:
        # Deactivate progress bar in debug mode since its updates make the
        # output very spammy
        progress_bar_settings["bar_template"] = ""

    with click.progressbar(
        repository.products, length=repository.products.count(), **progress_bar_settings
    ) as products:
        ledger = canadiantracker.triangle.ProductLedger(products)
        repository.add_product_price_samples(ledger)


if __name__ == "__main__":
    sys.exit(cli())  # pragma: no cover
