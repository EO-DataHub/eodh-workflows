from __future__ import annotations

import json
from pathlib import Path

import click
import geopandas as gpd
import shapely

from eodh_workflows.consts.directories import LOCAL_DATA_DIR
from eodh_workflows.utils.geom import geojson_to_polygon
from eodh_workflows.utils.logging import get_logger

_logger = get_logger(__name__)


@click.command(help="Generate smaller vector chips from larger geometry")
@click.option(
    "--aoi",
    required=True,
    help="Area of Interest as GeoJSON to be tiled; in EPSG:4326",
)
@click.option(
    "--chip_size_deg",
    default=0.2,
    help="Size of chips to generate in degrees",
)
@click.option(
    "--output_dir",
    required=False,
    type=click.Path(path_type=Path, resolve_path=True),  # type: ignore[type-var]
    help="Path to the output directory - will create new dir in CWD if not provided",
)
def chip_vector(aoi: str, output_dir: Path | None = None, chip_size_deg: float = 0.2) -> None:
    _logger.info(
        "Running with:\n%s",
        json.dumps(
            {
                "aoi": aoi,
                "output_dir": output_dir.as_posix() if output_dir is not None else None,
            },
            indent=4,
        ),
    )

    output_dir = output_dir or LOCAL_DATA_DIR / "vector-chips"
    output_dir.mkdir(exist_ok=True, parents=True)

    aoi_polygon = geojson_to_polygon(aoi)

    chips = generate_chips(aoi_polygon, chip_size_deg=chip_size_deg)
    feats = chips.to_geo_dict()
    feats_as_strs = []
    for idx, chip in enumerate(feats["features"]):
        output_chip_fp = output_dir / f"{idx:02d}.geojson"
        output_chip_fp.write_text(json.dumps(chip["geometry"], indent=4), encoding="utf-8")
        feats_as_strs.append(json.dumps(chip["geometry"]))

    (output_dir / "chips-full.geojson").write_text(json.dumps(feats_as_strs, indent=4), encoding="utf-8")


def generate_chips(aoi_geom: shapely.Polygon, chip_size_deg: float = 0.2) -> gpd.GeoDataFrame:
    """Tile the given AOI into smaller tiles of a fixed size in degrees."""
    # Get bounds of AOI
    minx, miny, maxx, maxy = aoi_geom.bounds

    # Create grid of tiles
    tiles = []
    x = minx
    while x < maxx:
        y = miny
        while y < maxy:
            tile = shapely.box(x, y, x + chip_size_deg, y + chip_size_deg)
            intersection = tile.intersection(aoi_geom)
            if not intersection.is_empty:
                tiles.append(intersection)
            y += chip_size_deg
        x += chip_size_deg

    # Create GeoDataFrame for tiles
    return gpd.GeoDataFrame(geometry=tiles, crs="EPSG:4326")
