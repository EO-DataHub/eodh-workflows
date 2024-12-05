from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import click
import numpy as np
import rioxarray
from tqdm import tqdm

from src.consts.directories import LOCAL_STAC_OUTPUT_DIR
from src.data_helpers.get_classes_dicts import get_classes
from src.geom_utils.calculate import calculate_geodesic_area
from src.local_stac.stac_io import read_local_stac, write_local_stac
from src.raster_utils.helpers import get_raster_polygon
from src.raster_utils.save import save_cog_v2
from src.utils.logging import get_logger

if TYPE_CHECKING:
    import xarray

_logger = get_logger(__name__)


@click.command(help="Generate LULC change")
@click.option(
    "--input_stac",
    required=True,
    type=click.Path(path_type=Path, resolve_path=True),  # type: ignore[type-var]
    help="Path to the local STAC folder",
)
@click.option(
    "--output_dir",
    required=False,
    type=click.Path(path_type=Path, resolve_path=True),  # type: ignore[type-var]
    help="Path to the output directory - will create new dir in CWD if not provided",
)
def generate_lulc_change(input_stac: Path, output_dir: Path | None = None) -> None:
    initial_arguments = {
        "input_stac": input_stac.as_posix(),
        "output_dir": output_dir.as_posix() if output_dir is not None else None,
    }
    _logger.info(
        "Running with:\n%s",
        json.dumps(initial_arguments, indent=4),
    )
    output_dir = output_dir or LOCAL_STAC_OUTPUT_DIR
    output_dir.mkdir(exist_ok=True, parents=True)

    local_stac = read_local_stac(input_stac)

    # Calculate the total number of assets with the role "data"
    total_data_assets = sum(
        sum(1 for asset in item.assets.values() if asset.roles and "data" in asset.roles)
        for item in local_stac.get_items(recursive=True)
    )

    progress_bar = tqdm(total=total_data_assets, desc="Generating change")
    for item in local_stac.get_items(recursive=True):
        for asset_key, asset in item.assets.items():
            if asset.roles and "data" in asset.roles:
                # Update the progress bar description with the current item and asset being processed
                progress_bar.set_description(f"Working with: {item.id}, asset: {asset_key}")

                # Get unique classes
                classes_orig_dict = asset.extra_fields["classification:classes"]
                classes_unique_values = get_classes(classes_orig_dict)

                raster_arr = rioxarray.open_rasterio(asset.href, masked=True)

                bounds_polygon = get_raster_polygon(raster_arr)
                area_m2 = calculate_geodesic_area(bounds_polygon)

                # Count occurrences for each class
                classes_shares: dict[str, float] = _get_shares_for_classes(raster_arr, classes_unique_values)
                raster_arr.attrs["classes_percentage"] = classes_shares

                classes_m2: dict[str, float] = _get_m2_for_classes(classes_shares, area_m2)
                raster_arr.attrs["classes_m2"] = classes_m2

                # Save COG with lulc change values in metadata
                raster_path = save_cog_v2(
                    arr=raster_arr, output_file_path=output_dir / Path(asset.href).relative_to(input_stac)
                )
                asset.href = raster_path.as_posix()
                if "size" in asset.extra_fields:
                    asset.extra_fields["size"] = raster_path.stat().st_size

                asset.extra_fields["classes_percentage"] = classes_shares
                asset.extra_fields["classes_m2"] = classes_m2

                # Increment the progress bar for each processed asset
                progress_bar.update(1)

    # Close the progress bar after processing is complete
    progress_bar.close()

    # Save local STAC
    write_local_stac(local_stac, output_dir, "EOPro LULC Change Generated", "EOPro LULC Change Generated")


def _get_m2_for_classes(percentage_dict: dict[str, float], full_area_m2: float) -> dict[str, float]:
    return {key: (value / 100) * full_area_m2 for key, value in percentage_dict.items()}


def _get_shares_for_classes(input_data: xarray.DataArray, unique_values: set[int]) -> dict[str, float]:
    data = input_data.to_numpy()
    # Remove NaN values from the array
    data = data[~np.isnan(data)]

    # Calculate unique values and their counts
    unique_values_for_array, counts = np.unique(data, return_counts=True)

    # Calculate shares for existing values
    counts_dict = {
        str(int(value)): float(count / data.size) * 100 for value, count in zip(unique_values_for_array, counts)
    }

    missing_values = unique_values.difference(set(unique_values_for_array))
    counts_dict.update({str(value): 0.0 for value in missing_values})

    return counts_dict
