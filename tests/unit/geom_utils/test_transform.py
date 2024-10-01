from __future__ import annotations

import pytest
from shapely.geometry import Polygon

from src.geom_utils.transform import gejson_to_polygon


def test_gejson_to_polygon() -> None:
    geojson_str = """
    {
        "type": "Polygon",
        "coordinates": [
            [
                [14.763294437090849, 50.833598186651244],
                [15.052268923898112, 50.833598186651244],
                [15.052268923898112, 50.989077215056824],
                [14.763294437090849, 50.989077215056824],
                [14.763294437090849, 50.833598186651244]
            ]
        ]
    }
    """
    polygon = gejson_to_polygon(geojson_str)

    corect_polygon = Polygon([
        (14.763294437090849, 50.833598186651244),
        (15.052268923898112, 50.833598186651244),
        (15.052268923898112, 50.989077215056824),
        (14.763294437090849, 50.989077215056824),
        (14.763294437090849, 50.833598186651244),
    ])

    assert polygon.equals(corect_polygon)


def test_geojson_to_polygon_point_provided() -> None:
    invalid_geojson = '{"type": "Point", "coordinates": [0.0, 0.0]}'
    with pytest.raises(ValueError, match="Provided GeoJSON is not a polygon"):
        gejson_to_polygon(invalid_geojson)


def test_geojson_to_polygon_invalid_geom() -> None:
    invalid_geom = '{"type": "Polygon","coordinates": [[[0, 0], [1, 1], [1, 2], [1, 1], [0, 0]]]}'
    with pytest.raises(ValueError, match="The provided polygon is not valid"):
        gejson_to_polygon(invalid_geom)
