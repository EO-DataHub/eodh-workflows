from __future__ import annotations

from typing import TYPE_CHECKING

import pyproj

if TYPE_CHECKING:
    from shapely.geometry import Polygon


def calculate_geodesic_area(polygon: Polygon) -> float:
    geod = pyproj.Geod(ellps="WGS84")
    lon, lat = polygon.exterior.coords.xy
    area, _ = geod.polygon_area_perimeter(lon, lat)
    # Return the area in square meters (area will be negative, so we take the absolute value)
    return float(abs(area))
