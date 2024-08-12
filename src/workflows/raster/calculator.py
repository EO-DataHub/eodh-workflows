from __future__ import annotations

import json
import warnings
from itertools import starmap
from pathlib import Path
from typing import TYPE_CHECKING

import click
import numpy as np
import planetary_computer as pc
import pyproj
import rioxarray  # noqa: F401
import stackstac
from pyproj import CRS
from pyproj.aoi import AreaOfInterest
from pyproj.database import query_utm_crs_info
from pystac_client import Client
from rasterio import features
from shapely.geometry import Polygon
from tqdm import tqdm

from src import consts
from src.utils.logging import get_logger
from src.workflows.raster.indices import calculate_index

if TYPE_CHECKING:
    import xarray
    from pystac import Item

warnings.filterwarnings("ignore", category=UserWarning, message="The argument 'infer_datetime_format'")

_logger = get_logger(__name__)
AREA_SQ_KM_THRESHOLD = 1000


@click.command(help="Calculate spectral index")
@click.option("--stac_collection", required=True, help="The name of the STAC collection to get the data from")
@click.option("--aoi", required=True, help="Area of Interest as GeoJSON")
@click.option("--date_start", required=True, help="Start date for the STAC query")
@click.option("--date_end", help="End date for the STAC query - will use current UTC date if not specified")
@click.option(
    "--index",
    default="NDVI",
    type=click.Choice(["NDVI", "NDWI", "EVI", "SAVI"], case_sensitive=False),
    show_default=True,
    help="The spectral index to calculate",
)
@click.option(
    "--output_dir",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    help="Path to the output directory - will create new dir in CWD if not provided",
)
def calculate(
    stac_collection: str,
    aoi: str,
    date_start: str,
    date_end: str,
    index: str,
    output_dir: Path | None = None,
) -> None:
    _logger.info(
        "Running with:\n%s",
        json.dumps(
            {
                "stac_collection": stac_collection,
                "aoi": aoi,
                "date_start": date_start,
                "date_end": date_end,
                "index": index,
                "output_dir": output_dir.as_posix() if output_dir is not None else None,
            },
            indent=4,
        ),
    )
    if output_dir is not None:
        output_dir.mkdir(exist_ok=True, parents=True)

    if stac_collection not in consts.stac.STAC_COLLECTIONS:
        msg = (
            f"Unknown STAC collection provided: `{stac_collection}`. "
            f"Available collections: {', '.join(consts.stac.STAC_COLLECTIONS)}"
        )
        raise ValueError(msg)

    if index.lower() not in consts.stac.INDEX_TO_ASSETS_LOOKUP[stac_collection]:
        msg = f"Calculating `{index}` index is not possible for STAC collection `{stac_collection}`"
        raise ValueError(msg)

    aoi_polygon = json.loads(aoi)
    bbox: tuple[int | float, int | float, int | float, int | float] = features.bounds(aoi_polygon)  # type: ignore[assignment]

    wgs84_crs = pyproj.CRS(consts.crs.WGS84)
    utm_crs = estimate_utm_crs(bbox)
    transformer = pyproj.Transformer.from_crs(wgs84_crs, utm_crs)
    utm_polygon = Polygon(list(starmap(transformer.transform, aoi_polygon["coordinates"][0])))

    if (area_sq_km := utm_polygon.area / 1_000_000) >= AREA_SQ_KM_THRESHOLD:
        msg = (
            f"The AOI you selected is too large ({area_sq_km} sq km). "
            f"Please provide an AOI below `{AREA_SQ_KM_THRESHOLD}` sq km."
        )
        raise ValueError(msg)

    # Connect to STAC API
    catalog = Client.open(consts.stac.CATALOG_API_ENDPOINT)

    # Define your search with CQL2 syntax
    search = catalog.search(
        filter_lang="cql2-json",
        filter={
            "op": "and",
            "args": [
                {"op": "s_intersects", "args": [{"property": "geometry"}, aoi_polygon]},
                {"op": "=", "args": [{"property": "collection"}, stac_collection]},
            ],
        },
        max_items=10,
    )

    items = [pc.sign(item) for item in search.item_collection()]

    for item in tqdm(items, desc="Processing items"):
        calculate_and_save_index(
            item=item,
            index=index.lower(),
            collection=stac_collection,
            bbox=bbox,
            output_dir=output_dir,
        )


def estimate_utm_crs(extent: tuple[float, float, float, float]) -> CRS:
    utm_crs_list = query_utm_crs_info(
        datum_name="WGS 84",
        area_of_interest=AreaOfInterest(*extent),
    )
    return CRS.from_epsg(utm_crs_list[0].code)


def calculate_and_save_index(
    item: Item,
    bbox: tuple[int | float, int | float, int | float, int | float],
    index: str,
    collection: str,
    output_dir: Path | None = None,
    epsg: int = 4326,
) -> None:
    raster_arr = build_raster_array(item=item, bbox=bbox, collection=collection, index=index, epsg=epsg)
    index_raster = calculate_index(index=index, raster_arr=raster_arr)
    save_raster(index_raster=index_raster, item_id=item.id, output_dir=output_dir, epsg=epsg)


def save_raster(index_raster: xarray.DataArray, item_id: str, output_dir: Path | None = None, epsg: int = 4326) -> None:
    if output_dir is None:
        output_dir = Path.cwd()
    index_raster = index_raster.rio.write_crs(f"EPSG:{epsg}")
    index_raster.rio.to_raster(output_dir / f"{item_id}.tif", driver="COG", windowed=True)


def build_raster_array(
    item: Item,
    bbox: tuple[int | float, int | float, int | float, int | float],
    collection: str,
    index: str,
    epsg: int = 4326,
) -> xarray.DataArray:
    assets_to_use = resolve_assets_for_index(index, collection)
    return (
        stackstac.stack(
            item,
            assets=assets_to_use,
            chunksize=consts.compute.CHUNK_SIZE,
            bounds_latlon=bbox,
            epsg=epsg,
        )
        .where(lambda x: x > 0, other=np.nan)  # sentinel-2 uses 0 as nodata
        .assign_coords(band=lambda x: x.common_name.rename("band"))  # use common names
    )


def resolve_assets_for_index(index: str, collection: str) -> list[str]:
    return consts.stac.INDEX_TO_ASSETS_LOOKUP[collection][index]
