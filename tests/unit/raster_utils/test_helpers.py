from __future__ import annotations

from unittest.mock import Mock

from shapely.geometry import Polygon, box

from src.utils.raster import get_raster_bounds


def test_get_raster_bounds() -> None:
    mock_xarray = Mock()
    mock_xarray.rio.bounds.return_value = (10.0, 20.0, 30.0, 40.0)
    mock_xarray.rio.crs.to_epsg.return_value = 4326

    result = get_raster_bounds(mock_xarray)

    assert isinstance(result, Polygon)

    expected_polygon = box(10.0, 20.0, 30.0, 40.0)
    assert result.equals(expected_polygon)

    mock_xarray.rio.bounds.assert_called_once()
