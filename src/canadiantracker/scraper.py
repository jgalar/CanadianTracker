import logging
import re
import signal
import sys
import textwrap
from types import FrameType

import click

from canadiantracker import cli_utils, model, triangle

logger = logging.getLogger(__name__)


def print_welcome():
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
def cli(debug: bool):
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
    product_listing_entry: model.ProductListingEntry,
) -> str:
    return product_listing_entry.name


def validate_category_levels(
    ctx: click.Context, param: click.Parameter, value: str | None
) -> str | None:
    """Validate that the category levels argument is a comman-separated list of
    integers."""
    if value is not None and not re.match(r"\d+(,\d+)*", value):
        raise click.BadParameter("format must be a comma-separated list of integers")

    return value


@cli.command(name="scrape-inventory", short_help="fetch static product properties")
@click.option(
    "--db-path",
    required=True,
    type=click.Path(),
    metavar="PATH",
    help="Path to sqlite db instance",
)
@click.option(
    "--category-levels",
    type=str,
    callback=validate_category_levels,
    default=None,
    metavar="LEVELS",
    help="Comma-separated list of category levels to scrape",
)
@click.option(
    "--dev-max-categories",
    type=int,
    default=0,
    help="Maximum number of categories to fetch (developer option)",
    metavar="NUM",
)
@click.option(
    "--dev-max-pages-per-category",
    default=0,
    type=int,
    help="Maximum number of pages to fetch per category (developer option)",
    metavar="NUM",
)
def scrape_inventory(
    db_path: str,
    category_levels: str,
    dev_max_categories: int,
    dev_max_pages_per_category: int,
):
    """
    Fetch static product properties.
    """

    if category_levels is not None:
        category_levels = [int(x) for x in category_levels.split(",")]

    repository = cli_utils.get_product_repository_from_sqlite_file_check_version(
        db_path
    )
    inventory = triangle.ProductInventory(
        category_levels_to_scrape=category_levels,
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
    type=click.Path(),
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
@click.option(
    "--discard-equal",
    help="Discard the previous last samples when equal to new samples",
    is_flag=True,
    show_default=True,
    default=False,
)
def scrape_prices(db_path: str, older_than: int, discard_equal: bool):
    """
    Fetch current product prices.
    """
    repository = cli_utils.get_product_repository_from_sqlite_file_check_version(
        db_path
    )

    progress_bar_settings = {
        "label": "Scraping prices",
        "show_pos": True,
        "item_show_func": lambda p: textwrap.shorten(
            p.code, width=32, placeholder="..."
        )
        if p
        else None,
    }

    if logging.root.level == logging.DEBUG:
        # Deactivate progress bar in debug mode since its updates make the
        # output very spammy
        progress_bar_settings["bar_template"] = ""

    with click.progressbar(
        repository.skus, length=repository.skus.count(), **progress_bar_settings
    ) as skus:
        ledger = triangle.ProductLedger(skus)
        repository.add_product_price_samples(ledger, discard_equal)


@cli.command(name="prune-samples", short_help="prune redundant samples")
@click.option(
    "--db-path",
    required=True,
    type=click.Path(),
    metavar="PATH",
    help="Path to sqlite db instance",
)
def prune_samples(db_path: str):
    repository = cli_utils.get_product_repository_from_sqlite_file_check_version(
        db_path
    )
    n_deleted = 0
    quit = False

    # Handle ctrl-C gracefully to avoid aborting (and rolling back) the changes
    # we have so far.
    def handle_sigint(signo: int, frame: FrameType):
        nonlocal quit
        quit = True

    signal.signal(signal.SIGINT, handle_sigint)

    def show_item(item: model.ProductInfoSample) -> str:
        nonlocal n_deleted

        return f"Deleted: {n_deleted}"

    with click.progressbar(
        repository.samples,
        repository.samples.count(),
        show_eta=False,
        show_pos=True,
        show_percent=True,
        item_show_func=show_item,
        update_min_steps=10000,
    ) as samples:
        # We need to flush periodically to avoid Python (SQLAlchemy) memory
        # usage to grow too much.  Flush at that many deletions.
        flush_batch_size = 10000

        # The goal is to keep each sample that is the start of a price interval
        # as well as the very last sample.
        #
        # Keep the last sample seen for each SKU index in `lastSamples`.  The
        # bool indicates if this sample is the start of a price interval.  So
        # basically, True if we should not delete that sample.  Samples are only
        # deleted when they are pushed out by a more recent sample, thus we
        # don't delete the very last sample for each SKU index.
        last_samples: dict[int, (model.ProductInfoSample, bool)] = dict()

        for sample in samples:
            last_sample_tuple = last_samples.get(sample.sku_index)
            if last_sample_tuple is None:
                last_samples[sample.sku_index] = (sample, True)
            else:
                last_sample, last_is_interval_start = last_sample_tuple

                assert sample.sample_time > last_sample.sample_time

                if not last_is_interval_start:
                    repository.delete_sample(last_sample)
                    n_deleted += 1

                    if n_deleted % flush_batch_size == 0:
                        repository.flush()

                is_interval_start = last_sample.price != sample.price
                last_samples[sample.sku_index] = (sample, is_interval_start)

            if quit:
                repository.flush()
                raise KeyboardInterrupt

        repository.vacuum()


if __name__ == "__main__":
    sys.exit(cli())  # pragma: no cover
