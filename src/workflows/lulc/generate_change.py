from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import click
import numpy as np
import pystac
import rioxarray
from tqdm import tqdm

from src.consts.directories import LOCAL_STAC_OUTPUT_DIR_DICT
from src.data_helpers.get_classes_dicts import get_classes
from src.geom_utils.calculate import calculate_geodesic_area
from src.raster_utils.helpers import get_raster_bounds
from src.raster_utils.save import save_cog
from src.utils.logging import get_logger

if TYPE_CHECKING:
    import xarray

_logger = get_logger(__name__)


@click.command(help="Generate LULC change")
@click.option(
    "--input_stac",
    required=True,
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    help="Path to the local STAC folder",
)
def generate_lulc_change(
    input_stac: Path,
) -> None:
    initial_arguments = {"input_stac": input_stac.as_posix()}
    _logger.info(
        "Running with:\n%s",
        json.dumps(initial_arguments, indent=4),
    )
    output_dir = LOCAL_STAC_OUTPUT_DIR_DICT["lulc_change"]
    output_dir.mkdir(exist_ok=True, parents=True)

    local_stac = pystac.Catalog.from_file((input_stac / "catalog.json").as_posix())
    local_stac.make_all_asset_hrefs_absolute()

    stac_items = local_stac.get_items()
    progress_bar = tqdm(stac_items, desc="Processing items")
    for item in progress_bar:
        progress_bar.set_description(f"Working with: {item.id}")

        classes_orig_dict = item.assets["data"].extra_fields["classification:classes"]
        classes_unique_values = get_classes(classes_orig_dict)

        raster_arr = rioxarray.open_rasterio(item.assets["data"].href, masked=True)

        bounds_polygon = get_raster_bounds(raster_arr)
        area_m2 = calculate_geodesic_area(bounds_polygon)

        # Count occurrences for each class
        classes_shares: dict[str, float] = _get_shares_for_classes(raster_arr, classes_unique_values)
        raster_arr.attrs["lulc_classes_percentage"] = classes_shares

        classes_m2: dict[str, float] = _get_m2_for_classes(classes_shares, area_m2)
        raster_arr.attrs["lulc_classes_m2"] = classes_m2

        # Save COG with lulc change values in metadata
        raster_path = save_cog(
            arr=raster_arr, item_id=item.id, epsg=item.properties["proj:epsg"], output_dir=output_dir
        )
        item.assets["data"].href = raster_path.as_posix()
        if "size" in item.assets["data"].extra_fields:
            item.assets["data"].extra_fields["size"] = raster_path.stat().st_size

        item.properties["lulc_classes_percentage"] = classes_shares
        item.properties["lulc_classes_m2"] = classes_m2

    local_stac.title = "EOPro LULC Change Generated"
    local_stac.description = "EOPro LULC Change Generated"
    local_stac.make_all_asset_hrefs_relative()
    local_stac.normalize_and_save(output_dir.as_posix(), catalog_type=pystac.CatalogType.SELF_CONTAINED)


def _get_m2_for_classes(percentage_dict: dict[str, float], full_area_m2: float) -> dict[str, float]:
    return {key: (value / 100) * full_area_m2 for key, value in percentage_dict.items()}


def _get_shares_for_classes(input_data: xarray.DataArray, unique_values: set[int]) -> dict[str, float]:
    data = input_data.to_numpy()
    unique_values_for_array, counts = np.unique(data, return_counts=True)

    counts_dict = {
        str(int(value)): float(count / data.size) * 100 for value, count in zip(unique_values_for_array, counts)
    }

    missing_values = unique_values.difference(set(unique_values_for_array))
    counts_dict.update({str(value): 0.0 for value in missing_values})

    return counts_dict
