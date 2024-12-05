from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click
import pystac
import rasterio
import rasterio.features
import rasterio.mask
from osgeo import gdal
from shapely.geometry.geo import box, mapping
from tqdm import tqdm

from src.consts.directories import LOCAL_STAC_OUTPUT_DIR_DICT
from src.geom_utils.transform import gejson_to_polygon
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from shapely.geometry import Polygon

_logger = get_logger(__name__)
gdal.UseExceptions()


def clip_raster(file_path: Path, aoi: Polygon, output_dir: Path) -> Path:
    output_dir.mkdir(exist_ok=True, parents=True)

    with rasterio.open(file_path) as src:
        out_image, out_transform = rasterio.mask.mask(src, [aoi], all_touched=True, crop=True)
        out_meta = src.meta.copy()

        out_meta.update({
            "driver": "COG",
            "height": out_image.shape[1],
            "width": out_image.shape[2],
            "transform": out_transform,
        })

    with rasterio.open(output_dir / file_path.name, "w", **out_meta) as dest:
        dest.write(out_image)

    return output_dir / file_path.name


@click.command(help="Clip (crop) rasters in STAC to specified AOI.")
@click.option(
    "--input_stac",
    required=True,
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    help="Path to the local STAC folder",
)
@click.option("--aoi", required=True, help="Area of Interest as GeoJSON to be used for clipping; in EPSG:4326")
def clip(input_stac: Path, aoi: str) -> None:
    _logger.info(
        "Running with:\n%s",
        json.dumps(
            {
                "input_stac": input_stac.as_posix(),
                "aoi": aoi,
            },
            indent=4,
        ),
    )
    output_dir = LOCAL_STAC_OUTPUT_DIR_DICT["clip"]
    aoi_polygon = gejson_to_polygon(aoi)

    local_stac = pystac.Catalog.from_file((input_stac / "catalog.json").as_posix())
    local_stac.make_all_asset_hrefs_absolute()

    stac_items = local_stac.get_items()
    progress_bar = tqdm(stac_items, desc="Processing items")
    for item in progress_bar:
        progress_bar.set_description(f"Working with: {item.id}")
        clipped_raster = clip_raster(file_path=Path(item.assets["data"].href), aoi=aoi_polygon, output_dir=output_dir)
        item.assets["data"].href = clipped_raster.as_posix()
        item.geometry = mapping(aoi_polygon)
        item.bbox = list(aoi_polygon.bounds)

        if "size" in item.assets["data"].extra_fields:
            item.assets["data"].extra_fields["size"] = clipped_raster.stat().st_size

    local_stac.title = "EOPro Clipped Data"
    local_stac.description = "EOPro Clipped Data"
    local_stac.make_all_asset_hrefs_relative()
    local_stac.normalize_and_save(output_dir.as_posix(), catalog_type=pystac.CatalogType.SELF_CONTAINED)
