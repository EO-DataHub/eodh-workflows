from __future__ import annotations

import click

from src.workflows.legacy.lulc.generate_change import generate_lulc_change
from src.workflows.legacy.raster.calculator import calculate
from src.workflows.legacy.raster.clip import clip
from src.workflows.legacy.water.quality import water_quality


@click.group()
def cli() -> None:
    """Earth Observation Data Hub operations."""


@cli.group()
def raster() -> None:
    """Raster operations and calculations."""


@cli.group()
def lulc() -> None:
    """Operations for Land Use Land Cover scenario."""


@cli.group()
def water() -> None:
    """Water quality operations and calculations."""


lulc.add_command(generate_lulc_change, name="change")
raster.add_command(calculate, name="calculate")
raster.add_command(clip, name="clip")
water.add_command(water_quality, name="quality")


if __name__ == "__main__":
    cli()
