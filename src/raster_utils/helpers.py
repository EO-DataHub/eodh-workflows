from __future__ import annotations

from typing import TYPE_CHECKING

from shapely.geometry import Polygon

if TYPE_CHECKING:
    import xarray


def get_raster_bounds(xarr: xarray.DataArray) -> Polygon:
    """Calculates bounds for the raster array."""
    min_lon = float(xarr.coords["x"].min())
    max_lon = float(xarr.coords["x"].max())
    min_lat = float(xarr.coords["y"].min())
    max_lat = float(xarr.coords["y"].max())

    lon_resolution = abs(xarr.coords["x"][1] - xarr.coords["x"][0])
    lat_resolution = abs(xarr.coords["y"][1] - xarr.coords["y"][0])

    min_lon -= lon_resolution / 2.0
    max_lon += lon_resolution / 2.0
    min_lat -= lat_resolution / 2.0
    max_lat += lat_resolution / 2.0

    polygon_coords = [
        (min_lon, min_lat),
        (min_lon, max_lat),
        (max_lon, max_lat),
        (max_lon, min_lat),
        (min_lon, min_lat),
    ]

    return Polygon(polygon_coords)
