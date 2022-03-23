================
Canadian Tracker
================
BeaverBeaverBeaver of the North
-------------------------------
Canadian Tracker tracks the inventory and prices of your favorite canadian
retailer using the internal API that powers
`CanadianTire.ca <https://www.canadiantire.ca>`_.

Due to the design of the Canadian Tire API and its relatively poor
performance, it does so in two steps implemented as two commands:
``scrape-inventory`` and ``scrape-prices``.

Use ``--help`` on any of the commands for more information on their role and options.

Getting Started
---------------

Canadian Tracker uses `poetry` to manage its dependancies. As such, you can
easily run the project from the development tree:

.. code-block:: console

  # Install all dependancies to a virtual environment
  $ poetry install


You then need to initialize the database, using `alembic`:

.. code-block:: console

   $ CTRACKER_DB_PATH=inventory.sqlite poetry run alembic upgrade head

You are then ready to start scraping the inventory, to get an up-to-date list
of products:

.. code-block:: console:

  $ poetry run ctscraper scrape-inventory --db-path inventory.sqlite

Once this is done, you can scrape the prices of the products in the inventory:

.. code-block:: console:

  $ poetry run ctscraper scrape-prices --db-path inventory.sqlite
