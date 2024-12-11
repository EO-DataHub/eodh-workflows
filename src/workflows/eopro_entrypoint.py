from __future__ import annotations

import click

from src.workflows.classification.summarize import summarize_classes
from src.workflows.ds.query import query
from src.workflows.raster.clip_v2 import clip_stac_items
from src.workflows.raster.reproject import reproject_stac_items
from src.workflows.spectral.index import spectral_index
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
def raster() -> None:
    """Raster related operations."""


@cli.group()
def spectral() -> None:
    """Spectral bands related operations."""


@cli.group()
def classification() -> None:
    """Discrete Datasets (e.g. Land Use / Land Cover) related operations."""


ds.add_command(query, name="query")
stac.add_command(join, name="join")
spectral.add_command(spectral_index, name="index")
raster.add_command(clip_stac_items, name="clip")
raster.add_command(reproject_stac_items, name="reproject")
classification.add_command(summarize_classes, name="summarize")


if __name__ == "__main__":
    cli()
