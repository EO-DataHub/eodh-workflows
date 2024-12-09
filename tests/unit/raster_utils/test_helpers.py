from __future__ import annotations

from unittest.mock import Mock

from shapely.geometry import Polygon, box

from src.utils.raster import get_raster_bounds


def test_get_raster_bounds() -> None:
    # Mockowanie xarray.DataArray i metody rio.bounds
    mock_xarray = Mock()
    mock_xarray.rio.bounds.return_value = (10.0, 20.0, 30.0, 40.0)

    # Wywołanie funkcji
    result = get_raster_bounds(mock_xarray)

    # Sprawdzenie czy zwrócony wynik to obiekt Polygon
    assert isinstance(result, Polygon)

    # Sprawdzenie czy współrzędne są prawidłowe
    expected_polygon = box(10.0, 20.0, 30.0, 40.0)
    assert result.equals(expected_polygon)

    # Sprawdzenie, czy metoda rio.bounds została wywołana
    mock_xarray.rio.bounds.assert_called_once()
