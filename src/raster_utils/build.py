from __future__ import annotations

from typing import TYPE_CHECKING

import stackstac

from src import consts
from src.data_helpers.sh_auth import sh_auth_token
from src.data_helpers.sh_get_data import sh_get_data

if TYPE_CHECKING:
    import xarray
    from pystac import Item


def build_raster_array(
    source, item: Item, bbox: tuple[int | float, int | float, int | float, int | float]
) -> xarray.DataArray:
    if source.catalog == consts.stac.CEDA_CATALOG_API_ENDPOINT:
        return stackstac.stack(
            item,
            assets=["GeoTIFF"],
            chunksize=consts.compute.CHUNK_SIZE,
            bounds_latlon=bbox,
            epsg=4326,
            resolution=(
                float(item.properties.get("geospatial_lon_resolution")),
                float(item.properties.get("geospatial_lat_resolution")),
            ),
        ).squeeze()
    if source.catalog == consts.stac.SH_CATALOG_API_ENDPOINT:
        token = sh_auth_token()
        return sh_get_data(token=token, source=source, bbox=bbox, stac_collection=source.collection, item_id=item.id)
    raise ValueError("Unsupported STAC catalog")
