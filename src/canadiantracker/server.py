import logging
import shlex
import tempfile
from typing import Optional

import click
import uvicorn

logger = logging.getLogger(__name__)


@click.group()
@click.option("-d", "--debug", is_flag=True, help="Set logging level to DEBUG")
@click.option("--log-file", help="Log file path")
def cli(debug: bool, log_file: Optional[str]):
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO, filename=log_file
    )


@cli.command()
@click.option(
    "--db-path",
    required=True,
    type=str,
    metavar="PATH",
    help="Path to sqlite db instance",
)
@click.option("--host", help="HTTP server listen interface", default="127.0.0.1")
@click.option("--port", help="HTTP server listen port", default=5000)
@click.option("--reload/--no-reload", help="Enable auto-reload", default=False)
def serve(db_path: str, host: str, port: int, reload: bool):
    """
    Serve the web UI and REST API on an HTTP server
    """
    with tempfile.NamedTemporaryFile(
        prefix="ctserver-serve-", suffix=".env", mode="w"
    ) as env_file:
        debug = logging.root.level == logging.DEBUG

        db_path = shlex.quote(db_path)
        print(f"CTSERVER_SERVE_DB_PATH={db_path}", file=env_file)
        env_file.flush()

        uvicorn.run(
            "canadiantracker.http:app",
            host=host,
            port=port,
            log_level="debug" if debug else "info",
            reload=reload,
            env_file=env_file.name,
        )
