from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pyproj
from shapely.geometry import shape

if TYPE_CHECKING:
    from shapely import Polygon


def geojson_to_polygon(geojson_str: str) -> Polygon:
    geojson = json.loads(geojson_str)
    if geojson["type"] != "Polygon":
        msg = "Provided GeoJSON is not a polygon"
        raise ValueError(msg)

    polygon = shape(geojson)
    if not polygon.is_valid:
        msg = "The provided polygon is not valid"
        raise ValueError(msg)

    return polygon


def calculate_geodesic_area(polygon: Polygon) -> float:
    geod = pyproj.Geod(ellps="WGS84")
    lon, lat = polygon.exterior.coords.xy
    area, _ = geod.polygon_area_perimeter(lon, lat)
    # Return the area in square meters (area will be negative, so we take the absolute value)
    return float(abs(area))
