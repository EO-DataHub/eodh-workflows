from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import click
import rasterio
import rasterio.mask
from pyproj import Transformer
from shapely.geometry.geo import mapping
from shapely.ops import transform
from tqdm import tqdm

from src.consts.crs import WGS84
from src.consts.directories import LOCAL_STAC_OUTPUT_DIR
from src.geom_utils.transform import gejson_to_polygon
from src.local_stac.stac_io import read_local_stac, write_local_stac
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from shapely.geometry import Polygon

_logger = get_logger(__name__)


@click.command(help="Clip (crop) rasters in STAC to specified AOI.")
@click.option(
    "--input_stac",
    required=True,
    type=click.Path(path_type=Path, resolve_path=True),  # type: ignore[type-var]
    help="Path to the local STAC folder",
)
@click.option("--area", required=True, help="Area of Interest as GeoJSON to be used for clipping; in EPSG:4326")
@click.option(
    "--output_dir",
    required=False,
    type=click.Path(path_type=Path, resolve_path=True),  # type: ignore[type-var]
    help="Path to the output directory - will create new dir in CWD if not provided",
)
def clip_stac_items(input_stac: Path, area: str, output_dir: Path | None = None) -> None:
    _logger.info(
        "Running with:\n%s",
        json.dumps(
            {
                "input_stac": input_stac.as_posix(),
                "aoi": area,
                "output_dir": output_dir.as_posix() if output_dir is not None else None,
            },
            indent=4,
        ),
    )

    output_dir = output_dir or LOCAL_STAC_OUTPUT_DIR
    output_dir.mkdir(exist_ok=True, parents=True)

    aoi_polygon = gejson_to_polygon(area)

    local_stac = read_local_stac(input_stac)

    # Calculate the total number of assets with the role "data"
    total_data_assets = sum(
        sum(1 for asset in item.assets.values() if asset.roles and "data" in asset.roles)
        for item in local_stac.get_items(recursive=True)
    )

    # Initialize a progress bar based on the number of "data" assets
    progress_bar = tqdm(total=total_data_assets, desc="Clipping assets")

    for item in local_stac.get_items(recursive=True):
        for asset_key, asset in item.assets.items():
            if asset.roles and "data" in asset.roles:
                # Update the progress bar description with the current item and asset being processed
                progress_bar.set_description(f"Working with: {item.id}, asset: {asset_key}")

                # Process the asset by clipping the raster
                asset_path = Path(asset.href)
                clipped_raster = _clip_raster(
                    file_path=asset_path,
                    aoi=aoi_polygon,
                    output_file_path=output_dir / asset_path.relative_to(input_stac),
                )

                # Update the asset's href to point to the clipped raster
                asset.href = clipped_raster.as_posix()

                # Update the size field in the asset's extra_fields if it exists
                if "size" in asset.extra_fields:
                    asset.extra_fields["size"] = clipped_raster.stat().st_size

                # Increment the progress bar for each processed asset
                progress_bar.update(1)

        # Update the item's geometry and bounding box with the AOI polygon
        item.geometry = mapping(aoi_polygon)
        item.bbox = list(aoi_polygon.bounds)

    # Close the progress bar after processing is complete
    progress_bar.close()

    # Save local STAC
    write_local_stac(local_stac, output_dir, "EOPro Clipped Data", "EOPro Clipped Data")


def _clip_raster(file_path: Path, aoi: Polygon, output_file_path: Path | None = None) -> Path:
    # Determine the output path
    output_file_path = file_path if output_file_path is None else output_file_path

    # Create the output directory if necessary
    if output_file_path is not None:
        output_file_path.parent.mkdir(exist_ok=True, parents=True)

    # Open the source raster
    with rasterio.open(file_path) as src:
        # Check if AOI CRS matches raster CRS
        raster_crs = src.crs
        aoi_crs = f"EPSG:{WGS84}"
        if raster_crs.to_string() != aoi_crs:
            transformer = Transformer.from_crs(aoi_crs, raster_crs.to_string(), always_xy=True)
            aoi = transform(transformer.transform, aoi)

        # Clip the raster using the AOI
        out_image, out_transform = rasterio.mask.mask(src, [aoi], all_touched=True, crop=True)

        # Replace nodata values with 0
        nodata_value = src.nodata if src.nodata is not None else 0

        # Update metadata
        out_meta = src.meta.copy()
        out_meta.update({
            "driver": "COG",  # Set driver to COG
            "height": out_image.shape[1],
            "width": out_image.shape[2],
            "transform": out_transform,
            "nodata": nodata_value,
        })

    # Write the clipped raster to the output path
    with rasterio.open(output_file_path, "w", **out_meta) as dest:
        dest.write(out_image)

    return output_file_path
