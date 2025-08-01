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

from eodh_workflows.consts.crs import WGS84
from eodh_workflows.consts.directories import LOCAL_DATA_DIR
from eodh_workflows.utils.geom import geojson_to_polygon
from eodh_workflows.utils.logging import get_logger
from eodh_workflows.utils.stac import read_local_stac, write_local_stac

if TYPE_CHECKING:
    from affine import Affine
    from shapely.geometry import Polygon

_logger = get_logger(__name__)


@click.command(help="Clip (crop) rasters in STAC to specified AOI.")
@click.option(
    "--data_dir",
    required=True,
    type=click.Path(path_type=Path, resolve_path=True),  # type: ignore[type-var]
    help="Path to the local STAC folder",
)
@click.option(
    "--aoi",
    required=True,
    help="Area of Interest as GeoJSON to be used for clipping; in EPSG:4326",
)
@click.option(
    "--output_dir",
    required=False,
    type=click.Path(path_type=Path, resolve_path=True),  # type: ignore[type-var]
    help="Path to the output directory - will create new dir in CWD if not provided",
)
def clip_stac_items(data_dir: Path, aoi: str, output_dir: Path | None = None) -> None:
    _logger.info(
        "Running with:\n%s",
        json.dumps(
            {
                "data_dir": data_dir.as_posix(),
                "aoi": aoi,
                "output_dir": output_dir.as_posix() if output_dir is not None else None,
            },
            indent=4,
        ),
    )

    output_dir = output_dir or LOCAL_DATA_DIR / "raster-clip"
    output_dir.mkdir(exist_ok=True, parents=True)

    aoi_polygon = geojson_to_polygon(aoi)

    local_stac = read_local_stac(data_dir)

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
                clipped_raster_fp = _clip_raster(
                    file_path=asset_path,
                    aoi=aoi_polygon,
                    output_file_path=output_dir / asset_path.relative_to(data_dir),
                )

                # Update the asset's href to point to the clipped raster
                asset.href = clipped_raster_fp.as_posix()

                # Update the size field in the asset's extra_fields if it exists
                if "size" in asset.extra_fields:
                    asset.extra_fields["size"] = clipped_raster_fp.stat().st_size

                # Update asset PROJ metadata
                src: rasterio.DatasetReader
                if "proj:shape" in asset.extra_fields or "proj:transform" in asset.extra_fields:
                    with rasterio.open(asset_path) as src:
                        src_transform: Affine = src.transform
                        shape = src.shape
                    asset.extra_fields["proj:shape"] = shape
                    asset.extra_fields["proj:transform"] = list(src_transform)

                # Increment the progress bar for each processed asset
                progress_bar.update(1)

        # Update the item's geometry and bounding box with the AOI polygon
        item.geometry = mapping(aoi_polygon)
        item.bbox = list(aoi_polygon.bounds)

    # Close the progress bar after processing is complete
    progress_bar.close()

    # Save local STAC
    write_local_stac(local_stac, output_dir, "EOPro Clipped Data", "EOPro Clipped Data")


def _clip_raster(
    file_path: Path,
    aoi: Polygon,
    output_file_path: Path,
    nodata_val: float | None = None,
) -> Path:
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

        # Replace nodata values if needed
        nodata_value = src.nodata if src.nodata is not None else nodata_val

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
