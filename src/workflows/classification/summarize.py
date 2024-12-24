from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import click
import numpy as np
import rioxarray
from tqdm import tqdm

from src.consts.directories import LOCAL_DATA_DIR
from src.utils.geom import calculate_geodesic_area
from src.utils.logging import get_logger
from src.utils.raster import get_raster_polygon, save_cog_v2
from src.utils.stac import read_local_stac, write_local_stac
from src.workflows.legacy.lulc.helpers import get_classes

if TYPE_CHECKING:
    import xarray

_logger = get_logger(__name__)


@click.command(help="Generate LULC change")
@click.option(
    "--data_dir",
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
def summarize_classes(data_dir: Path, output_dir: Path | None = None) -> None:
    initial_arguments = {
        "data_dir": data_dir.as_posix(),
        "output_dir": output_dir.as_posix() if output_dir is not None else None,
    }
    _logger.info(
        "Running with:\n%s",
        json.dumps(initial_arguments, indent=4),
    )

    output_dir = output_dir or LOCAL_DATA_DIR / "classification-summarize"
    output_dir = output_dir.absolute()
    output_dir.mkdir(exist_ok=True, parents=True)
    data_dir = data_dir.absolute()

    local_stac = read_local_stac(data_dir)
    local_stac.make_all_asset_hrefs_absolute()

    # Calculate the total number of assets with the role "data"
    for item in tqdm(list(local_stac.get_items(recursive=True)), desc="Generating class summaries"):
        for asset_key, asset in item.assets.items():
            asset_out_fp = (output_dir / Path(asset.href).relative_to(data_dir)).absolute()
            if not (
                (asset.roles and "data" in asset.roles)
                or (asset.extra_fields.get("role", []) and "data" in asset.extra_fields.get("role", []))
            ):
                _logger.info("Asset %s cannot be summarized. Copying to output dir as is.", asset_key)
                shutil.copy(Path(asset.href), asset_out_fp)
                asset.href = asset_out_fp
                continue

            # Get unique classes
            classes_orig_list = asset.extra_fields["classification:classes"]
            classes_unique_values = get_classes(classes_orig_list)

            raster_arr = rioxarray.open_rasterio(asset.href, masked=True)

            bounds_polygon = get_raster_polygon(raster_arr)
            area_m2 = calculate_geodesic_area(bounds_polygon)

            # Count occurrences for each class
            classes_shares: dict[int, float] = _get_shares_for_classes(raster_arr, classes_unique_values)
            raster_arr.attrs["classes_percentage"] = classes_shares

            classes_m2: dict[int, float] = _get_m2_for_classes(classes_shares, area_m2)
            raster_arr.attrs["classes_m2"] = classes_m2

            # Save COG with lulc change values in metadata
            raster_path = save_cog_v2(arr=raster_arr, output_file_path=asset_out_fp)
            asset.href = raster_path.as_posix()
            if "size" in asset.extra_fields:
                asset.extra_fields["size"] = raster_path.stat().st_size

            for class_spec in classes_orig_list:
                if "color_hint" in class_spec:
                    class_spec["color-hint"] = class_spec.pop("color_hint")
                class_spec["percentage"] = classes_shares[class_spec["value"]]
                class_spec["area_m2"] = classes_m2[class_spec["value"]]
                class_spec["area_km2"] = classes_m2[class_spec["value"]] / 1e6

    # Save local STAC
    write_local_stac(local_stac, output_dir, "EOPro LULC Change", "EOPro LULC Change Generated")


def _get_m2_for_classes(percentage_dict: dict[int, float], full_area_m2: float) -> dict[int, float]:
    return {key: (value / 100) * full_area_m2 for key, value in percentage_dict.items()}


def _get_shares_for_classes(input_data: xarray.DataArray, unique_values: set[int]) -> dict[int, float]:
    data = input_data.to_numpy()
    # Remove NaN values from the array
    data = data[~np.isnan(data)]

    # Calculate unique values and their counts
    unique_values_for_array, counts = np.unique(data, return_counts=True)

    # Calculate shares for existing values
    counts_dict = {int(value): float(count / data.size) * 100 for value, count in zip(unique_values_for_array, counts)}

    missing_values = unique_values.difference(set(unique_values_for_array))
    counts_dict.update(dict.fromkeys(missing_values, 0.0))

    return counts_dict
