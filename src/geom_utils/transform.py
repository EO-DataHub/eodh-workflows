from __future__ import annotations

import json

from shapely.geometry import Polygon, shape


def gejson_to_polygon(geojson_str: str) -> Polygon:
    geojson = json.loads(geojson_str)
    if geojson["type"] != "Polygon":
        msg = "Provided GeoJSON is not a polygon"
        raise ValueError(msg)

    polygon = shape(geojson)
    if not polygon.is_valid:
        msg = "The provided polygon is not valid"
        raise ValueError(msg)

    return polygon
