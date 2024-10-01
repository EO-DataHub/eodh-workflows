from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import click
import numpy as np
from pystac import Item
from pystac_client import Client
from shapely.geometry import Polygon, mapping
from tqdm import tqdm

from src import consts
from src.geom_utils.calculate import calculate_geodesic_area
from src.geom_utils.transform import gejson_to_polygon
from src.local_stac.generate import generate_stac, prepare_stac_item
from src.raster_utils.build import build_raster_array
from src.raster_utils.helpers import get_raster_bounds
from src.raster_utils.save import save_cog
from src.utils.logging import get_logger

if TYPE_CHECKING:
    import xarray
    from pystac import Item

_logger = get_logger(__name__)


@click.command(help="Generate LULC change")
@click.option("--aoi", required=True, help="The area of interest as GeoJSON in EPSG:4326")
@click.option("--start_date", required=True, help="Start date in ISO 8601 used to search input data")
@click.option("--end_date", required=True, help="End date in ISO 8601 used to search input data")
def generate_lulc_change(aoi: str, start_date: str, end_date: str) -> None:
    _logger.info(
        "Running with:\n%s", json.dumps({"aoi": aoi, "start_date": start_date, "end_date": end_date}, indent=4)
    )

    # Transferring the AOI
    aoi_polygon = gejson_to_polygon(aoi)

    items = _get_data(aoi_polygon, start_date, end_date)

    # Calculating lulc change
    stac_items: list[Item] = []
    # Get unique classes
    # For the first item only, the rest is the same
    classes_orig_dict: list[dict[str, int | str]] = items[0].assets["GeoTIFF"].extra_fields["classification:classes"]
    classes_unique_values: set[int] = {int(raster_value["value"]) for raster_value in classes_orig_dict}

    progress_bar = tqdm(items, desc="Processing items")
    for item in progress_bar:
        progress_bar.set_description(f"Working with: {item.id}")

        # Get additional properties of the item
        epsg = int(item.properties.get("proj:code").replace("EPSG:", ""))
        transform = item.properties.get("proj:transform")

        # Build array
        raster_arr = build_raster_array(
            item=item,
            bbox=aoi_polygon.bounds,
            epsg=epsg,
            assets=["GeoTIFF"],
            resolution=(
                float(item.properties.get("geospatial_lon_resolution")),
                float(item.properties.get("geospatial_lat_resolution")),
            ),
        )

        bounds_polygon = get_raster_bounds(raster_arr)
        area_m2 = calculate_geodesic_area(bounds_polygon)

        # Count occurrences for each class
        classes_shares: dict[str, float] = _get_shares_for_classes(raster_arr, classes_unique_values)
        raster_arr.attrs["lulc_classes_percentage"] = classes_shares

        classes_m2: dict[str, float] = _get_m2_for_classes(classes_shares, area_m2)
        raster_arr.attrs["lulc_classes_m2"] = classes_m2

        # Save COG with lulc change values in metadata
        raster_path = save_cog(index_raster=raster_arr, item_id=item.id, output_dir=Path.cwd(), epsg=4326)

        # Create STAC definition for each item processed
        # Include lulc change in STAC item properties
        stac_items.append(
            prepare_stac_item(
                file_path=raster_path,
                id_item=item.id,
                geometry=bounds_polygon,
                epsg=epsg,
                transform=transform,
                datetime=item.datetime,
                start_datetime=item.properties.get("start_datetime"),
                end_datetime=item.properties.get("end_datetime"),
                additional_prop={"lulc_classes_percentage": classes_shares, "lulc_classes_m2": classes_m2},
                asset_extra_fields={"classification:classes": classes_orig_dict},
            )
        )

    # Generate local STAC for processed data
    generate_stac(items=stac_items, geometry=bounds_polygon, start_date=start_date, end_date=end_date)


def _get_data(aoi_polygon: Polygon, start_date: str, end_date: str) -> list[Item]:
    # Connect to STAC API
    catalog = Client.open(consts.stac.CEDA_CATALOG_API_ENDPOINT)
    stac_collection = consts.stac.CEDA_ESACCI_LC_COLLECTION_NAME

    # Querying the data
    search = catalog.search(
        filter_lang="cql2-json",
        filter={
            "op": "and",
            "args": [
                {"op": "s_intersects", "args": [{"property": "geometry"}, mapping(aoi_polygon)]},
                {"op": "=", "args": [{"property": "collection"}, stac_collection]},
                {"op": ">=", "args": [{"property": "datetime"}, start_date]},
                {"op": "<=", "args": [{"property": "datetime"}, end_date]},
            ],
        },
    )

    return sorted(search.items(), key=lambda item: item.datetime)


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
