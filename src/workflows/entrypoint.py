from __future__ import annotations

import click

from src.workflows.raster.calculator import calculate


@click.group()
def cli() -> None:
    """Earth Observation Data Hub operations."""


@cli.group()
def raster() -> None:
    """Raster operations and calculations."""


raster.add_command(calculate, name="calculate")

if __name__ == "__main__":
    cli()
