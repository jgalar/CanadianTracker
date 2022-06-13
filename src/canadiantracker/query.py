import click
import requests
import json
import pprint
import sys
import logging
import textwrap
import decimal
from collections.abc import Iterator
from canadiantracker.cli_utils import (
    get_product_repository_from_sqlite_file_check_version,
)

import canadiantracker.storage
import canadiantracker.model


logger = logging.getLogger(__name__)


@click.group()
@click.option("-d", "--debug", is_flag=True, help="Set logging level to DEBUG")
def cli(debug: bool, args=None) -> None:
    """
    CanadianTracker tracks the inventory and prices of your favorite canadian
    retailer using the internal API that powers canadiantire.ca.

    \b
    ctquery supports the following commands:
      - price-history:
        get the price history of a product

    Use --help on any of the commands for more information on their role and options.
    """
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO)


@cli.command(name="price-history", short_help="print price history for a product")
@click.option(
    "--db-path",
    required=True,
    type=str,
    metavar="PATH",
    help="Path to sqlite db instance",
)
@click.option(
    "--format",
    type=click.Choice(["plot", "json"], case_sensitive=False),
    default="json",
    help="Query output format (default: json)",
)
@click.argument("product_code", nargs=1)
def price_history(db_path: str, format: str, product_code: str) -> None:
    """
    Fetch product properties.
    """

    # Normalize to upper case as product codes are presented under various
    # capitalization patterns by the website and APIs.
    product_code = product_code.upper()

    repository = get_product_repository_from_sqlite_file_check_version(db_path)

    if repository.get_product_listing_by_code(product_code) is None:
        click.echo(
            click.style("Error: ", fg="red", bold=True)
            + "No product with code "
            + click.style(product_code, fg="white", bold=True)
        )
        return sys.exit(1)

    product_info = repository.get_product_listing_by_code(product_code)
    product_samples = repository.get_product_info_samples_by_code(product_code)
    if format == "json":
        json_history(product_info, product_samples)
    elif format == "plot":
        plot_history(product_info, product_samples)


def plot_history(
    product_info: canadiantracker.model.ProductInfo,
    product_samples: Iterator[canadiantracker.model.ProductInfoSample],
):
    import plotext as plt

    plt.datetime.set_datetime_form(date_form="%d/%m/%Y")

    prices = [float(sample.price) for sample in product_samples]
    dates = [
        plt.datetime.datetime_to_string(sample.sample_time)
        for sample in product_samples
    ]

    prices = []
    dates = []

    for index, sample in enumerate(product_samples):
        formatted_date = plt.datetime.datetime_to_string(sample.sample_time)
        price = float(
            sample.price.quantize(
                decimal.Decimal(".01"), rounding=decimal.ROUND_HALF_EVEN
            )
        )
        if index == 0:
            dates.append(formatted_date)
            prices.append(price)
            continue

        # When a price changes, insert the previous price at the same date
        # to force plotext to show prices as "steps" rather than a line
        # connecting the prices.
        if price != prices[-1]:
            dates.append(formatted_date)
            prices.append(prices[-1])

        dates.append(formatted_date)
        prices.append(price)

    plt.canvas_color("black")
    plt.ticks_color("red")
    plt.axes_color("black")
    plt.plot_date(dates, prices, color="white")

    plt.title("Price history for {}".format(product_info.name))
    plt.xlabel("Date")
    plt.ylabel("Price $")
    plt.show()


def json_history(
    product_info: canadiantracker.model.ProductInfo,
    product_samples: Iterator[canadiantracker.model.ProductInfoSample],
):
    import json

    # Since the json package doesn't allow us to dump from a generator and
    # we don't want to expand the whole query result into a temporary list,
    # we generate the array's brackets and commas and serialize the elements
    # one by one.
    print("[", end="")
    for index, sample in enumerate(product_samples):
        if index > 0:
            print(", ", end="")

        print(
            json.dumps(
                {
                    "datetime": sample.sample_time.isoformat(),
                    "price": "{:.2f}".format(sample.price),
                },
            ),
            end="",
        )
    print("]")


if __name__ == "__main__":
    sys.exit(cli())  # pragma: no cover
