"""add skus table

Revision ID: 9169a7c5bda3
Revises: 4e2a96338a6c
Create Date: 2022-06-20 09:59:54.418820

"""
from alembic import op
import sqlalchemy as sa
import re


# revision identifiers, used by Alembic.
revision = "9169a7c5bda3"
down_revision = "4e2a96338a6c"
branch_labels = None
depends_on = None


# Ensure the formatting of `sku` is "123-4567-8" (i.e. add the possibly missing
# leading zeros).
def normalize_formatted_sku_code(sku):
    if re.match(r"\d-\d\d\d\d-\d", sku):
        sku = "0" + sku

    if re.match(r"\d\d-\d\d\d\d-\d", sku):
        sku = "0" + sku

    if not re.match(r"\d\d\d-\d\d\d\d-\d", sku):
        raise RuntimeError(f"Unexpected sku code format: `{sku}`")

    return sku


# Convert a formatted SKU code (123-4567-8) to its "internal" form (1234567).
def sku_code_from_formatted_sku_code(c):
    assert re.match(r"\d\d\d-\d\d\d\d-\d", c)
    return c[0:3] + c[4:8]


def upgrade():
    db = op.get_bind()

    metadata = sa.MetaData()
    products_static_table = sa.Table(
        "products_static", metadata, autoload_with=op.get_bind().engine
    )
    products_dynamic_table = sa.Table(
        "products_dynamic", metadata, autoload_with=op.get_bind().engine
    )

    # Store all SKU values to insert here, do one batch insert at the end.
    sku_values = []

    # In the current schema, for products with multiple SKUs, the `sku` column
    # of the `products_static` table contains a `|`-separated list of SKU codes,
    # like:
    #
    #   9-0309-0|9-0308-2|9-0307-4|9-0328-4
    #
    # In this migration, we introduce a separate `skus` table, where each SKU
    # gets an entry.  We then drop the `sku` column of the `products_static`
    # table.

    # For each product...
    print(">>> Reading product list, generating SKU list")
    added_sku_codes = set()
    for (
        index,
        name,
        product_code,
        is_in_clearance,
        last_listed,
        url,
        sku_codes,
    ) in db.execute(sa.select(products_static_table)):
        if sku_codes is None:
            # Some entries in the Official Database don't contain a SKU, maybe
            # because they are stale... in any case, we can't do anything with
            # those right now.
            continue

        # For each SKU code...
        for formatted_sku_code in sku_codes.split("|"):
            formatted_sku_code = normalize_formatted_sku_code(formatted_sku_code)
            sku_code = sku_code_from_formatted_sku_code(formatted_sku_code)

            if sku_code in added_sku_codes:
                db_entry = {
                    "index": index,
                    "name": name,
                    "product_code": product_code,
                    "is_in_clearance": is_in_clearance,
                    "last_listed": last_listed,
                    "url": url,
                    "sku_codes": sku_codes,
                }
                print("Duplicate sku entry, ignoring an entry: " + str(db_entry))
                continue

            sku_values.append(
                {
                    "code": sku_code,
                    "formatted_code": formatted_sku_code,
                    "product_index": index,
                }
            )

            added_sku_codes.add(sku_code)

    print(">>> Creating skus table")
    # Now that we know the data looks sane, create the new table.
    skus_table = op.create_table(
        "skus",
        sa.Column("index", sa.Integer, nullable=False),
        sa.Column("code", sa.String, nullable=False),
        sa.Column("formatted_code", sa.String),
        sa.Column("product_index", sa.Integer, nullable=False),
        sa.ForeignKeyConstraint(
            ["product_index"],
            ["products_static.index"],
        ),
        sa.PrimaryKeyConstraint("index"),
    )

    # Create an index on skus.code, we'll want to look up SKUs by code.
    op.create_index(None, "skus", ["code"], unique=True)

    # Insert SKU rows.
    op.bulk_insert(skus_table, sku_values)

    # Build an in-memory sku code -> sku index map, to speed up lookups lower
    # (avoid doing millions of SQL queries when migrating the samples).
    sku_code_to_index = {}
    for (index, code, formatted_code, product_index) in db.execute(
        sa.select(skus_table)
    ):
        sku_code_to_index[code] = index

    print(">>> Dropping products_static.sku column")
    # Drop the `sku` column.
    op.drop_column("products_static", "sku")

    # Create a new table for the samples
    print(">>> Creating samples table")
    samples_table = op.create_table(
        "samples",
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("sample_time", sa.DateTime(), nullable=False),
        sa.Column("sku_index", sa.String(), nullable=False),
        sa.Column("price", sa.Numeric(), nullable=False),
        sa.Column("in_promo", sa.Boolean(), nullable=False),
        sa.Column("raw_payload", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["sku_index"],
            ["skus.index"],
        ),
        sa.PrimaryKeyConstraint("index"),
    )

    # Go over each sample.
    print(">>> Generating new sample values")
    i = 0
    sample_values = []
    sample_count = db.execute(
        sa.select(sa.func.count(products_dynamic_table.columns.index))
    ).fetchone()[0]
    for index, sample_time, code, price, in_promo, raw_payload in db.execute(
        sa.select(products_dynamic_table)
    ):
        raw = eval(raw_payload)

        # Only keep samples that have an explicit SKU value.
        if "SKU" not in raw:
            continue

        if raw["PriceFrom"] == "Y":
            continue

        sku_code = raw["SKU"]

        # There are products for which we didn't have a SKU list (maybe items
        # that don't exist anymore?), so there is no SKU row for those.
        #
        # For those, see if there is a product with that code, and create a SKU
        # entry from that.
        if sku_code not in sku_code_to_index:
            print(f"Could not find SKU with code {sku_code}")
            prod_row = db.execute(
                sa.text(
                    'SELECT "index" FROM products_static WHERE code = :sku_code LIMIT 1'
                ),
                {"sku_code": sku_code + "P"},
            ).first()
            if prod_row is not None:
                product_index = prod_row[0]
                print(
                    f"  -> Found a product with that code (index {product_index}), creating a SKU from that"
                )
                ret = db.execute(
                    sa.insert(skus_table).values(
                        {"code": sku_code, "product_index": product_index}
                    )
                )

                # Maintain our in-memory sku code -> sku index map.
                sku_index = ret.inserted_primary_key[0]
                sku_code_to_index[sku_code] = sku_index
            else:
                # No SKU nor product with that code.  Weird, but there's nothing we can do.
                print("  -> Could not find product with that code, dropping sample")
                continue

        sku_index = sku_code_to_index[sku_code]

        sample_values.append(
            {
                "sample_time": sample_time,
                "sku_index": sku_index,
                "price": price,
                "in_promo": in_promo,
                "raw_payload": raw_payload,
            }
        )

        i += 1
        if i % 10000 == 0:
            print(f"{i}/{sample_count}")

    print(">>> Inserting new samples")
    op.bulk_insert(samples_table, sample_values)

    print(">>> Dropping products_dynamic table")
    op.drop_table("products_dynamic")


def downgrade():
    # No way I'm implementing this.
    raise NotImplementedError
