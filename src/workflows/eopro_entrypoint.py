from __future__ import annotations

import click

from src.workflows.ds.query import query


@click.group()
def cli() -> None:
    """EOPro Funcs CLI."""


@cli.group()
def ds() -> None:
    """Dataset related operations."""


ds.add_command(query, name="query")


if __name__ == "__main__":
    cli()
