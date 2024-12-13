from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import click
import rasterio
import rasterio.mask
import rioxarray
from tqdm import tqdm

from src.consts.directories import LOCAL_DATA_DIR
from src.utils.logging import get_logger
from src.utils.stac import read_local_stac, write_local_stac

if TYPE_CHECKING:
    from affine import Affine

_logger = get_logger(__name__)


@click.command(help="Clip (crop) rasters in STAC to specified AOI.")
@click.option(
    "--data_dir",
    required=True,
    type=click.Path(path_type=Path, resolve_path=True),  # type: ignore[type-var]
    help="Path to the local STAC folder",
)
@click.option(
    "--epsg",
    required=True,
    help="EPSG code to use for reprojection",
)
@click.option(
    "--output_dir",
    required=False,
    type=click.Path(path_type=Path, resolve_path=True),  # type: ignore[type-var]
    help="Path to the output directory - will create new dir in CWD if not provided",
)
def reproject_stac_items(data_dir: Path, epsg: str, output_dir: Path | None = None) -> None:
    _logger.info(
        "Running with:\n%s",
        json.dumps(
            {
                "data_dir": data_dir.as_posix(),
                "epsg": epsg,
                "output_dir": output_dir.as_posix() if output_dir is not None else None,
            },
            indent=4,
        ),
    )

    output_dir = output_dir or LOCAL_DATA_DIR / "raster-reproject"
    output_dir.mkdir(exist_ok=True, parents=True)

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
                reprojected_raster_fp = _reproject_raster(
                    file_path=asset_path,
                    epsg=epsg,
                    output_file_path=output_dir / asset_path.relative_to(data_dir),
                )

                # Update the asset's href to point to the clipped raster
                asset.href = reprojected_raster_fp.as_posix()

                # Update the size field in the asset's extra_fields if it exists
                if "size" in asset.extra_fields:
                    asset.extra_fields["size"] = reprojected_raster_fp.stat().st_size

                # Update asset PROJ metadata
                src: rasterio.DatasetReader
                with rasterio.open(reprojected_raster_fp) as src:
                    src_transform: Affine = src.transform
                    shape = src.shape
                    asset.extra_fields["proj:shape"] = shape
                    asset.extra_fields["proj:transform"] = list(src_transform)
                    asset.extra_fields["proj:epsg"] = src.crs.to_epsg()
                    item.properties["proj:epsg"] = src.crs.to_epsg()
                    item.properties.pop("proj:transform", None)
                    item.properties.pop("proj:shape", None)

                # Increment the progress bar for each processed asset
                progress_bar.update(1)

    # Close the progress bar after processing is complete
    progress_bar.close()

    # Save local STAC
    write_local_stac(local_stac, output_dir, "EOPro Reprojected Data", "EOPro Reprojected Data")


def _reproject_raster(
    file_path: Path,
    epsg: str,
    output_file_path: Path,
) -> Path:
    # Create the output directory if necessary
    output_file_path.parent.mkdir(exist_ok=True, parents=True)

    # Open the source raster
    arr = rioxarray.open_rasterio(file_path)
    arr = arr.rio.reproject(epsg)
    arr.rio.to_raster(output_file_path)

    return output_file_path
