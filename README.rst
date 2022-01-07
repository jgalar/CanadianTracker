================
Canadian Tracker
================
BeaverBeaverBeaver of the North
-------------------------------
CanadianTracker tracks the inventory and prices of your favorite canadian
retailer using the internal API that powers canadiantire.ca.

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
  $ poetry run ctscraper
