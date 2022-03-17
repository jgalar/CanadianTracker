import click
import requests
import json
import pprint
import shlex
import sys
import logging
import textwrap
import tempfile
import uvicorn
from typing import Optional

import canadiantracker.triangle
import canadiantracker.storage
import canadiantracker.model


logger = logging.getLogger(__name__)
logging_to_terminal = False


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
@click.option("--log-file", help="Log file path")
def cli(debug: bool, log_file: Optional[str], args=None) -> None:
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
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO, filename=log_file
    )

    global logging_to_terminal
    logging_to_terminal = log_file is None


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
def scrape_inventory(db_path: str) -> None:
    """
    Fetch static product properties.
    """

    repository = canadiantracker.storage.get_product_repository_from_sqlite_file(
        db_path, should_create=True
    )
    inventory = canadiantracker.triangle.ProductInventory()

    progress_bar_settings = {
        "label": "Scraping inventory",
        "show_pos": True,
        "item_show_func": lambda p: textwrap.shorten(
            p.name, width=32, placeholder="..."
        )
        if p
        else None,
    }

    if logging.root.level == logging.DEBUG and logging_to_terminal:
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
    repository = canadiantracker.storage.get_product_repository_from_sqlite_file(
        db_path, should_create=True
    )

    progress_bar_settings = {
        "label": "Scraping prices",
        "show_pos": True,
        "item_show_func": lambda p: textwrap.shorten(
            p.name, width=32, placeholder="..."
        )
        if p
        else None,
    }

    if logging.root.level == logging.DEBUG and logging_to_terminal:
        # Deactivate progress bar in debug mode since its updates make the
        # output very spammy
        progress_bar_settings["bar_template"] = ""

    with click.progressbar(
        repository.products, length=repository.products.count(), **progress_bar_settings
    ) as products:
        ledger = canadiantracker.triangle.ProductLedger(products)
        repository.add_product_price_samples(ledger)


@cli.command(
    name="serve-http", short_help="serve the web UI and REST API on an HTTP server"
)
@click.option(
    "--db-path",
    required=True,
    type=str,
    metavar="PATH",
    help="Path to sqlite db instance",
)
@click.option("-p", "--port", help="HTTP server listen port", default=5000)
def serve_http(db_path: str, port: int) -> None:
    """
    Serve the web UI and REST API on an HTTP server
    """
    with tempfile.NamedTemporaryFile(
        prefix="ctscraper-http-", suffix=".env", mode="w"
    ) as env_file:
        debug = logging.root.level == logging.DEBUG

        db_path = shlex.quote(db_path)
        print(f"CTSCRAPER_HTTP_DB_PATH={db_path}", file=env_file)
        env_file.flush()

        uvicorn.run(
            "canadiantracker.http:app",
            host="127.0.0.1",
            port=port,
            log_level="debug" if debug else "info",
            reload=debug,
            env_file=env_file.name,
        )


if __name__ == "__main__":
    sys.exit(cli())  # pragma: no cover
