import click
import sys
import logging
import decimal
from canadiantracker import cli_utils
from canadiantracker import model


logger = logging.getLogger(__name__)


@click.group()
@click.option("-d", "--debug", is_flag=True, help="Set logging level to DEBUG")
def cli(debug: bool) -> None:
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


@cli.command(name="price-history", short_help="print price history for a SKU")
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
@click.argument("sku_code", nargs=1)
def price_history(db_path: str, format: str, sku_code: str) -> None:
    """
    Fetch SKU properties.
    """
    repository = cli_utils.get_product_repository_from_sqlite_file_check_version(
        db_path
    )

    sku = repository.get_sku_by_formatted_code(sku_code)
    if sku is None:
        click.echo(
            click.style("Error: ", fg="red", bold=True)
            + "No SKU with code "
            + click.style(sku_code, fg="white", bold=True)
        )
        return sys.exit(1)

    if format == "json":
        json_history(sku)
    elif format == "plot":
        plot_history(sku)


def plot_history(sku: model.Sku) -> None:
    import plotext as plt

    plt.datetime.set_datetime_form(date_form="%d/%m/%Y")

    prices = [float(sample.price) for sample in sku.samples]
    dates = [
        plt.datetime.datetime_to_string(sample.sample_time) for sample in sku.samples
    ]

    prices = []
    dates = []

    for index, sample in enumerate(sku.samples):
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

    plt.title("Price history for {}".format(sku.product.name))
    plt.xlabel("Date")
    plt.ylabel("Price $")
    plt.show()


def json_history(sku: model.Sku) -> None:
    import json

    # Since the json package doesn't allow us to dump from a generator and
    # we don't want to expand the whole query result into a temporary list,
    # we generate the array's brackets and commas and serialize the elements
    # one by one.
    print("[", end="")
    for index, sample in enumerate(sku.samples):
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
