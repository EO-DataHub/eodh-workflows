from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

import click
import numpy as np
from pystac import Item
from pystac_client import Client
from shapely.geometry import Polygon, mapping
from tqdm import tqdm

from src import consts
from src.data_helpers.get_classes_dicts import get_classes, get_classes_orig_dict
from src.data_helpers.sh_auth import sh_auth_token
from src.geom_utils.calculate import calculate_geodesic_area
from src.geom_utils.transform import gejson_to_polygon
from src.local_stac.generate import generate_stac, prepare_stac_item
from src.raster_utils.build import build_raster_array
from src.raster_utils.helpers import get_raster_bounds
from src.raster_utils.save import save_cog
from src.raster_utils.thumbnail import generate_thumbnail
from src.utils.logging import get_logger

if TYPE_CHECKING:
    import xarray
    from pystac import Item

_logger = get_logger(__name__)


@dataclass
class DataSource:
    name: str
    catalog: str
    collection: str


DATASOURCE_LOOKUP = {
    consts.stac.CEDA_ESACCI_LC_LOCAL_NAME: DataSource(
        name=consts.stac.CEDA_ESACCI_LC_LOCAL_NAME,
        catalog=consts.stac.CEDA_CATALOG_API_ENDPOINT,
        collection=consts.stac.CEDA_ESACCI_LC_COLLECTION_NAME,
    ),
    consts.stac.SH_CLMS_CORINELC_LOCAL_NAME: DataSource(
        name=consts.stac.SH_CLMS_CORINELC_LOCAL_NAME,
        catalog=consts.stac.SH_CATALOG_API_ENDPOINT,
        collection=consts.stac.SH_CLMS_CORINELC_COLLECTION_NAME,
    ),
    consts.stac.SH_CLMS_WATER_BODIES_LOCAL_NAME: DataSource(
        name=consts.stac.SH_CLMS_WATER_BODIES_LOCAL_NAME,
        catalog=consts.stac.SH_CATALOG_API_ENDPOINT,
        collection=consts.stac.SH_CLMS_WATER_BODIES_COLLECTION_NAME,
    ),
}


@click.command(help="Generate LULC change")
@click.option(
    "--source",
    type=click.Choice(DATASOURCE_LOOKUP.keys(), case_sensitive=True),
    required=True,
    help="Source dataset to use",
)
@click.option("--aoi", required=True, help="The area of interest as GeoJSON in EPSG:4326")
@click.option("--start_date", required=True, help="Start date in ISO 8601 used to search input data")
@click.option("--end_date", required=True, help="End date in ISO 8601 used to search input data")
def generate_lulc_change(source: str, aoi: str, start_date: str, end_date: str) -> None:
    initial_arguments = {"source": source, "aoi": aoi, "start_date": start_date, "end_date": end_date}
    _logger.info(
        "Running with:\n%s",
        json.dumps(initial_arguments, indent=4),
    )
    source_ds: DataSource = DATASOURCE_LOOKUP[source]
    # Transferring the AOI
    aoi_polygon = gejson_to_polygon(aoi)

    items = _get_data(source_ds, aoi_polygon, start_date, end_date)

    classes_orig_dict = get_classes_orig_dict(source_ds, items[0])
    classes_unique_values = get_classes(classes_orig_dict)

    # Calculating lulc change
    stac_items: list[Item] = []

    progress_bar = tqdm(items, desc="Processing items")
    for item in progress_bar:
        progress_bar.set_description(f"Working with: {item.id}")

        # Build array
        raster_arr = build_raster_array(source=source_ds, item=item, bbox=aoi_polygon.bounds)

        bounds_polygon = get_raster_bounds(raster_arr)
        area_m2 = calculate_geodesic_area(bounds_polygon)

        # Count occurrences for each class
        classes_shares: dict[str, float] = _get_shares_for_classes(raster_arr, classes_unique_values)
        raster_arr.attrs["lulc_classes_percentage"] = classes_shares

        classes_m2: dict[str, float] = _get_m2_for_classes(classes_shares, area_m2)
        raster_arr.attrs["lulc_classes_m2"] = classes_m2

        # Save COG with lulc change values in metadata
        raster_path = save_cog(index_raster=raster_arr, item_id=item.id, epsg=4326)
        generate_thumbnail(raster_arr, raster_path=raster_path, classes_list=classes_orig_dict)

        # Create STAC definition for each item processed
        # Include lulc change in STAC item properties
        stac_items.append(
            prepare_stac_item(
                file_path=raster_path,
                id_item=item.id,
                geometry=bounds_polygon,
                epsg=raster_arr.rio.crs.to_epsg(),
                transform=list(raster_arr.rio.transform()),
                datetime=item.datetime,
                additional_prop={"lulc_classes_percentage": classes_shares, "lulc_classes_m2": classes_m2},
                asset_extra_fields={"classification:classes": classes_orig_dict},
            )
        )

    # Generate local STAC for processed data
    generate_stac(items=stac_items, title="eodh lulc change", description=json.dumps(initial_arguments))


def _get_data(source: DataSource, aoi_polygon: Polygon, start_date: str, end_date: str) -> list[Item]:
    # Sentinel Hub requires authentication
    token = sh_auth_token() if source.catalog == consts.stac.SH_CATALOG_API_ENDPOINT else None

    # Connect to STAC API
    catalog = Client.open(source.catalog, headers={"Authorization": f"Bearer {token}"})
    stac_collection = source.collection

    # Querying the data
    search = catalog.search(
        collections=[stac_collection], datetime=f"{start_date}/{end_date}", intersects=mapping(aoi_polygon)
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
