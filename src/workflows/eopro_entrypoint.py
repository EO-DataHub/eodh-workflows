from __future__ import annotations

import click

from src.workflows.ds.query import query
from src.workflows.lulc.generate_change_v2 import generate_lulc_change
from src.workflows.stac.clip import clip_stac_items
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


@cli.group()
def classification() -> None:
    """Discreta Datasets (e.g. Land Use / Land Cover) related operations."""


ds.add_command(query, name="query")
stac.add_command(join, name="join")
stac.add_command(clip_stac_items, name="clip")
classification.add_command(generate_lulc_change, name="summarize")


if __name__ == "__main__":
    cli()
