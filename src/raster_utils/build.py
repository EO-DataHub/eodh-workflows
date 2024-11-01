from __future__ import annotations

from typing import TYPE_CHECKING

import stackstac

from src import consts
from src.consts.crs import WGS84
from src.data_helpers.sh_auth import sh_auth_token
from src.data_helpers.sh_get_data import sh_get_data

if TYPE_CHECKING:
    import xarray
    from pystac import Item

    from src.workflows.lulc.generate_change import DataSource


def build_raster_array(
    source: DataSource,
    item: Item,
    bbox: tuple[int | float, int | float, int | float, int | float],
    epsg: int = WGS84,
) -> xarray.DataArray:
    if source.catalog == consts.stac.CEDA_CATALOG_API_ENDPOINT:
        return (
            stackstac.stack(
                item,
                assets=["GeoTIFF"],
                chunksize=consts.compute.CHUNK_SIZE,
                bounds_latlon=bbox,
                epsg=epsg,
                resolution=(
                    float(item.properties.get("geospatial_lon_resolution")),
                    float(item.properties.get("geospatial_lat_resolution")),
                ),
            )
            .squeeze()
            .compute()
        )
    if source.catalog == consts.stac.SH_CATALOG_API_ENDPOINT:
        token = sh_auth_token()
        return sh_get_data(token=token, source=source, bbox=bbox, stac_collection=source.collection, item_id=item.id)
    error_message = "Unsupported STAC catalog"
    raise ValueError(error_message)
