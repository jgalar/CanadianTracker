================
Canadian Tracker
================

Canadian Tracker tracks the inventory and prices of your favorite canadian
retailer using the internal API that powers
`CanadianTire.ca <https://www.canadiantire.ca>`_.

Due to the design of the Canadian Tire API and its relatively poor
performance, it does so in multiple steps implemented as the following commands:
``scrape-products``, ``scrape-skus``, and ``scrape-prices``.

Use ``--help`` on any of the commands for more information on their role and options.

Getting Started
---------------

Canadian Tracker uses `poetry` to manage its Python dependencies. As such, you
can easily run the project from the development tree:

.. code-block:: console

  # Install all dependencies to a virtual environment
  $ poetry install


You then need to initialize the database, using `alembic`:

.. code-block:: console

   $ CTRACKER_DB_PATH=inventory.sqlite poetry run alembic upgrade head

You are then ready to start scraping the inventory, to get an up-to-date list
of products:

.. code-block:: console:

  $ poetry run ctscraper scrape-products --db-path inventory.sqlite
  $ poetry run ctscraper scrape-skus --db-path inventory.sqlite

Once this is done, you can scrape the prices of the products in the inventory:

.. code-block:: console:

  $ poetry run ctscraper scrape-prices --db-path inventory.sqlite

The web interface is an npm project with its root in `src/canadiantracker/web`.
Build it with:

.. code-block:: console:

  $ cd src/canadiantracker/web
  $ npm install
  $ npm run build-dev # or build-prod

The Javascript and CSS output files will be placed in
`src/canadiantracker/web/dist` and will be picked up by the web application.
