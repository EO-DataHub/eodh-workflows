from __future__ import annotations

import json
from typing import TYPE_CHECKING

import click

from src.utils.logging import get_logger

if TYPE_CHECKING:
    from pathlib import Path

_logger = get_logger(__name__)


@click.command(help="Calculate spectral index")
@click.option("--stac_collection", required=True, help="The name of the STAC collection to get the data from")
@click.option("--aoi", required=True, help="Area of Interest as GeoJSON")
@click.option("--date_start", required=True, help="Start date for the STAC query")
@click.option("--date_end", help="End date for the STAC query - will use current UTC date if not specified")
@click.option(
    "--index",
    default="NDVI",
    type=click.Choice(["NDVI", "NDWI", "EVI"], case_sensitive=False),
    show_default=True,
    help="The spectral index to calculate",
)
@click.option(
    "--output_dir",
    type=click.Path(),
    help="Path to the output directory - will create new dir in CWD if not provided",
)
def calculate(  # noqa: PLR0913, PLR0917
    stac_collection: str,
    aoi: str,
    date_start: str,
    date_end: str,
    index: str,
    output_dir: Path | None = None,
) -> None:
    _logger.info(
        "Running with %s",
        json.dumps(
            {
                "stac_collection": stac_collection,
                "aoi": aoi,
                "date_start": date_start,
                "date_end": date_end,
                "index": index,
                "output_dir": output_dir,
            },
            indent=4,
        ),
    )
