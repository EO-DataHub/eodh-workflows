from __future__ import annotations

from unittest.mock import MagicMock

from shapely.geometry import Polygon

from src.raster_utils.helpers import get_raster_bounds  # Change to the correct module name


def test_get_raster_bounds() -> None:
    # Mocking the xarray.DataArray
    mock_xarr = MagicMock()

    # Mocking the coordinates for 'x' and 'y'
    mock_xarr.coords = {"x": MagicMock(), "y": MagicMock()}

    # Setting up min and max values for 'x' and 'y' coordinates
    mock_xarr.coords["x"].min.return_value = 10.0  # Minimum longitude
    mock_xarr.coords["x"].max.return_value = 20.0  # Maximum longitude
    mock_xarr.coords["y"].min.return_value = 30.0  # Minimum latitude
    mock_xarr.coords["y"].max.return_value = 40.0  # Maximum latitude

    # Simulating resolution (difference between coordinates)
    mock_xarr.coords["x"].__getitem__.side_effect = [10.0, 11.0]  # Difference of 1.0
    mock_xarr.coords["y"].__getitem__.side_effect = [30.0, 31.0]  # Difference of 1.0

    # Call the function
    result_polygon = get_raster_bounds(mock_xarr)

    # Expected polygon coordinates
    expected_polygon = Polygon([(9.5, 29.5), (9.5, 40.5), (20.5, 40.5), (20.5, 29.5), (9.5, 29.5)])

    # Assert that the returned polygon matches the expected polygon
    assert result_polygon.equals(expected_polygon)
