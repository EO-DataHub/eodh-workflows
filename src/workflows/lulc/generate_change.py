from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import click
import numpy as np
from pystac import Item
from pystac_client import Client
from shapely.geometry import mapping, shape
from tqdm import tqdm

from src import consts
from src.local_stac.generate import generate_stac, prepare_stac_item
from src.raster_utils.build import build_raster_array
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
    # Connect to STAC API
    catalog = Client.open(consts.stac.CEDA_CATALOG_API_ENDPOINT)
    stac_collection = consts.stac.CEDA_ESACCI_LC_COLLECTION_NAME

    _logger.info(
        "Running with:\n%s", json.dumps({"aoi": aoi, "start_date": start_date, "end_date": end_date}, indent=4)
    )

    # Transferring the AOI
    aoi_geojson = json.loads(aoi)
    if aoi_geojson["type"] != "Polygon":
        msg = "Provided GeoJSON is not a polygon"
        raise ValueError(msg)
    aoi_polygon = shape(aoi_geojson)

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
    items = sorted(search.items(), key=lambda item: item.datetime)

    # Calculating lulc change
    classes_shares: list[dict[str, int]] = []
    stac_items: list[Item] = []

    progress_bar = tqdm(items, desc="Processing items")
    for idx, item in enumerate(progress_bar):
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

        # Count occurrences for each class
        classes_shares.append(_get_counts_for_classes(raster_arr))

        # Save COG with lulc change values in metadata
        # Change is calculated based on the previously processed item
        if idx > 0:
            change = _calculate_percentage_change(classes_shares[idx], classes_shares[idx - 1])
            raster_arr.attrs["lulc_change_percentage"] = change
            raster_path = save_cog(index_raster=raster_arr, item_id=item.id, output_dir=Path.cwd(), epsg=4326)
        else:
            change = {}
            raster_path = save_cog(index_raster=raster_arr, item_id=item.id, output_dir=Path.cwd(), epsg=4326)

        # Create STAC definition for each item processed
        # Include lulc change in STAC item properties
        stac_items.append(
            prepare_stac_item(
                file_path=raster_path,
                id_item=item.id,
                geometry=aoi_polygon,
                epsg=epsg,
                transform=transform,
                datetime=item.datetime,
                start_datetime=item.properties.get("start_datetime"),
                end_datetime=item.properties.get("end_datetime"),
                additional_prop={"lulc_change_percentage": change},
            )
        )

    # Generate local STAC for processed data
    generate_stac(items=stac_items, geometry=aoi_polygon, start_date=start_date, end_date=end_date)


def _get_counts_for_classes(input_data: xarray.DataArray) -> dict[str, int]:
    data = input_data.to_numpy()
    unique_values, counts = np.unique(data, return_counts=True)
    return dict(zip(unique_values, counts))


def _calculate_percentage_change(current_dict: dict[str, int], previous_dict: dict[str, int]) -> dict[str, float]:
    """Calculates the percentage change of class counts between two dictionaries.

    Parameters:
    current_dict (dict): Dictionary with current class counts (from current xarray).
    previous_dict (dict): Dictionary with previous class counts (from previous xarray).

    Returns:
    dict: A dictionary with percentage changes for each class.

    """
    percentage_change = {}

    # Pobieramy wszystkie unikalne klucze (klasy) z obu słowników
    all_classes = set(current_dict.keys()).union(set(previous_dict.keys()))

    for class_value in all_classes:
        if class_value in current_dict and class_value in previous_dict:
            # Class exists in both current and previous dictionaries
            current_count = current_dict[class_value]
            previous_count = previous_dict[class_value]

            # Calculate the percentage change
            change = ((current_count - previous_count) / previous_count) * 100
            percentage_change[class_value] = change

        elif class_value in current_dict and class_value not in previous_dict:
            # Class appears only in the current dictionary (new class)
            percentage_change[class_value] = 100
        elif class_value not in current_dict and class_value in previous_dict:
            # Class disappeared (exists only in the previous dictionary)
            percentage_change[class_value] = -100

    return percentage_change
