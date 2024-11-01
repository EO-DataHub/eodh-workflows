from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
import numpy as np
import rasterio
import rasterio.features
import rasterio.mask
from osgeo import gdal
from shapely.geometry.geo import box, mapping

from src.consts.directories import LOCAL_STAC_OUTPUT_DIR
from src.utils.logging import get_logger

_logger = get_logger(__name__)
gdal.UseExceptions()


def clip_raster(fp: Path, aoi: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(exist_ok=True, parents=True)

    with rasterio.open(fp) as src:
        out_image, out_transform = rasterio.mask.mask(src, [aoi], nodata=np.nan, crop=True)
        out_meta = src.meta

    out_meta.update({
        "driver": "GTiff",
        "height": out_image.shape[1],
        "width": out_image.shape[2],
        "transform": out_transform,
        "nodata": np.nan,
    })

    with rasterio.open(output_dir / fp.name, "w", **out_meta) as dest:
        dest.write(out_image)

    return output_dir / fp.name


def update_item_with_new_footprint(stac_item_spec: dict[str, Any], aoi_polygon: dict[str, Any]) -> dict[str, Any]:
    bbox = rasterio.features.bounds(aoi_polygon)
    footprint_poly = box(*bbox)
    footprint = mapping(footprint_poly)
    stac_item_spec["bbox"] = bbox
    stac_item_spec["geometry"] = footprint
    return stac_item_spec


@click.command(help="Clip (crop) raster to specified AOI.")
@click.option(
    "--stac_item_spec",
    required=True,
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    help="The STAC item metadata associated with raster file",
)
@click.option(
    "--raster",
    required=True,
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    help="GeoTiff raster file to clip",
)
@click.option("--aoi", required=True, help="Area of Interest as GeoJSON to be used for clipping")
@click.option(
    "--output_dir",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    help="Path to the output directory - will create new dir in CWD if not provided",
)
def clip(
    stac_item_spec: Path,
    raster: Path,
    aoi: str,
    output_dir: Path | None = None,
) -> None:
    _logger.info(
        "Running with:\n%s",
        json.dumps(
            {
                "stac_item_spec": stac_item_spec.as_posix(),
                "raster": raster.as_posix(),
                "aoi": aoi,
                "output_dir": output_dir.as_posix() if output_dir is not None else None,
            },
            indent=4,
        ),
    )
    output_dir = output_dir or LOCAL_STAC_OUTPUT_DIR

    # Clip
    aoi_polygon = json.loads(aoi)
    clip_raster(fp=raster, output_dir=output_dir, aoi=aoi_polygon)

    # Update Item spec with new footprint and bbox
    item = update_item_with_new_footprint(
        stac_item_spec=json.loads(stac_item_spec.read_text(encoding="utf-8")),
        aoi_polygon=aoi_polygon,
    )

    (output_dir / stac_item_spec.name).write_text(json.dumps(item, indent=4), encoding="utf-8")
