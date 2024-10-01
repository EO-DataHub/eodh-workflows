from __future__ import annotations

from typing import TYPE_CHECKING

import stackstac

from src import consts

if TYPE_CHECKING:
    import xarray
    from pystac import Item


def build_raster_array(
    item: Item,
    bbox: tuple[int | float, int | float, int | float, int | float],
    assets: list[str],
    epsg: int,
    resolution: tuple[float, float],
) -> xarray.DataArray:
    return stackstac.stack(
        item, assets=assets, chunksize=consts.compute.CHUNK_SIZE, bounds_latlon=bbox, epsg=epsg, resolution=resolution
    ).squeeze()
