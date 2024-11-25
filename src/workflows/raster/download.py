from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

import click
from pystac_client import Client
from shapely.geometry import Polygon, mapping
from tqdm import tqdm

from src import consts
from src.data_helpers.get_classes_dicts import get_classes_orig_dict
from src.data_helpers.sh_auth import sh_auth_token
from src.geom_utils.transform import gejson_to_polygon
from src.local_stac.generate import generate_stac, prepare_stac_item
from src.raster_utils.build import build_raster_array
from src.raster_utils.helpers import get_raster_bounds
from src.raster_utils.save import save_cog
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from pystac import Item


_logger = get_logger(__name__)


@dataclass
class DataSource:
    name: str
    catalog: str
    collection: str
    epsg: int


DATASOURCE_LOOKUP = {
    consts.stac.CEDA_ESACCI_LC_LOCAL_NAME: DataSource(
        name=consts.stac.CEDA_ESACCI_LC_LOCAL_NAME,
        catalog=consts.stac.CEDA_CATALOG_API_ENDPOINT,
        collection=consts.stac.CEDA_ESACCI_LC_COLLECTION_NAME,
        epsg=consts.crs.WGS84,
    ),
    consts.stac.SH_CLMS_CORINELC_LOCAL_NAME: DataSource(
        name=consts.stac.SH_CLMS_CORINELC_LOCAL_NAME,
        catalog=consts.stac.SH_CATALOG_API_ENDPOINT,
        collection=consts.stac.SH_CLMS_CORINELC_COLLECTION_NAME,
        epsg=consts.crs.WGS84,
    ),
    consts.stac.SH_CLMS_WATER_BODIES_LOCAL_NAME: DataSource(
        name=consts.stac.SH_CLMS_WATER_BODIES_LOCAL_NAME,
        catalog=consts.stac.SH_CATALOG_API_ENDPOINT,
        collection=consts.stac.SH_CLMS_WATER_BODIES_COLLECTION_NAME,
        epsg=consts.crs.WGS84,
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
@click.option("--date_start", required=True, help="Start date in ISO 8601 used to search input data")
@click.option("--date_end", required=True, help="End date in ISO 8601 used to search input data")
def download_data(
    source: str,
    aoi: str,
    date_start: str,
    date_end: str,
) -> None:
    initial_arguments = {"source": source, "aoi": aoi, "date_start": date_start, "date_end": date_end}
    _logger.info(
        "Running with:\n%s",
        json.dumps(initial_arguments, indent=4),
    )
    output_dir = consts.directories.LOCAL_STAC_OUTPUT_DIR_DICT["download"]
    output_dir.mkdir(exist_ok=True, parents=True)

    source_ds: DataSource = DATASOURCE_LOOKUP[source]
    aoi_polygon = gejson_to_polygon(aoi)

    items = _get_data(source_ds, aoi_polygon, date_start, date_end)

    classes_orig_dict = get_classes_orig_dict(source_ds, items[0])

    stac_items: list[Item] = []
    progress_bar = tqdm(items, desc="Processing items")
    for item in progress_bar:
        progress_bar.set_description(f"Working with: {item.id}")

        # Build array
        raster_arr = build_raster_array(source=source_ds, item=item, bbox=aoi_polygon.bounds)
        bounds_polygon = get_raster_bounds(raster_arr)

        raster_path = save_cog(arr=raster_arr, item_id=item.id, epsg=source_ds.epsg, output_dir=output_dir)

        stac_items.append(
            prepare_stac_item(
                file_path=raster_path,
                id_item=item.id,
                geometry=bounds_polygon,
                epsg=raster_arr.rio.crs.to_epsg(),
                transform=list(raster_arr.rio.transform()),
                datetime=item.datetime,
                additional_prop={
                    "workflow_metadata": {
                        "stac_collection": source,
                        "date_start": date_start,
                        "date_end": date_end,
                        "aoi": mapping(aoi_polygon),
                    },
                },
                asset_extra_fields={
                    "classification:classes": classes_orig_dict,
                },
            )
        )

    generate_stac(
        items=stac_items,
        output_dir=output_dir,
        title="EOPro Downloaded Data",
        description="EOPro Downloaded Data",
    )


def _get_data(source: DataSource, aoi_polygon: Polygon, date_start: str, date_end: str) -> list[Item]:
    # Sentinel Hub requires authentication
    token = sh_auth_token() if source.catalog == consts.stac.SH_CATALOG_API_ENDPOINT else None

    # Connect to STAC API
    catalog = Client.open(source.catalog, headers={"Authorization": f"Bearer {token}"})
    stac_collection = source.collection

    # Querying the data
    search = catalog.search(
        collections=[stac_collection], datetime=f"{date_start}/{date_end}", intersects=mapping(aoi_polygon)
    )

    return sorted(search.items(), key=lambda item: item.datetime)
