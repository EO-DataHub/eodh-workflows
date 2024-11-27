from __future__ import annotations

import click

from src.workflows.ds.query import query
from src.workflows.stac.join import join


@click.group()
def cli() -> None:
    """EOPro Funcs CLI."""


@cli.group()
def ds() -> None:
    """Dataset related operations."""


@cli.group()
def stac() -> None:
    """STAC related operations."""


ds.add_command(query, name="query")
stac.add_command(join, name="join")


if __name__ == "__main__":
    cli()
