from __future__ import annotations

from typing import TYPE_CHECKING

from shapely.geometry import Polygon, box

if TYPE_CHECKING:
    import xarray


def get_raster_bounds(xarr: xarray.DataArray) -> Polygon:
    """Calculates bounds for the raster array."""
    bbox = xarr.rio.bounds()
    minx, miny, maxx, maxy = bbox

    return box(minx, miny, maxx, maxy)
