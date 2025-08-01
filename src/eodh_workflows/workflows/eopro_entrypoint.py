from __future__ import annotations

import click

from eodh_workflows.workflows.classification.summarize import summarize_classes
from eodh_workflows.workflows.ds.query import query
from eodh_workflows.workflows.raster.clip import clip_stac_items
from eodh_workflows.workflows.raster.reproject import reproject_stac_items
from eodh_workflows.workflows.raster.thumbnail import generate_thumbnail_for_stac_items
from eodh_workflows.workflows.spectral.index import spectral_index
from eodh_workflows.workflows.stac.join import join, join_v2
from eodh_workflows.workflows.vector.chip import chip_vector
from eodh_workflows.workflows.water.quality import water_quality


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


@cli.group()
def water() -> None:
    """Water quality related operations."""


@cli.group()
def vector() -> None:
    """Vector related operations."""


ds.add_command(query, name="query")
stac.add_command(join, name="join")
stac.add_command(join_v2, name="join_v2")
spectral.add_command(spectral_index, name="index")
raster.add_command(clip_stac_items, name="clip")
raster.add_command(reproject_stac_items, name="reproject")
raster.add_command(generate_thumbnail_for_stac_items, name="thumbnail")
classification.add_command(summarize_classes, name="summarize")
water.add_command(water_quality, name="quality")
vector.add_command(chip_vector, name="chip")


if __name__ == "__main__":
    cli()
