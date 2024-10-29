from __future__ import annotations

import click

from src.workflows.lulc.generate_change import generate_lulc_change
from src.workflows.raster.calculator import calculate
from src.workflows.raster.clip import clip


@click.group()
def cli() -> None:
    """Earth Observation Data Hub operations."""


@cli.group()
def lulc() -> None:
    """Operations for Land Use Land Cover scenario."""


lulc.add_command(generate_lulc_change, name="change")


@cli.group()
def raster() -> None:
    """Raster operations and calculations."""


raster.add_command(calculate, name="calculate")
raster.add_command(clip, name="clip")


if __name__ == "__main__":
    cli()
