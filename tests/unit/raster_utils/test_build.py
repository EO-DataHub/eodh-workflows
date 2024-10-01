from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import xarray as xr
from pystac import Item

from src import consts  # Assuming consts is in src
from src.raster_utils.build import build_raster_array  # Replace with the actual module path


@pytest.fixture()
def example_item() -> MagicMock:
    # Create a mock pystac.Item or use a real one for testing
    return MagicMock(spec=Item)


@pytest.fixture()
def example_bbox() -> tuple[int, int, int, int]:
    return (0, 0, 1, 1)


@pytest.fixture()
def example_assets() -> list[str]:
    return ["asset1", "asset2"]


@pytest.fixture()
def example_epsg() -> int:
    return 4326


@pytest.fixture()
def example_resolution() -> tuple[float, float]:
    return (0.1, 0.1)


@patch("src.raster_utils.build.stackstac.stack")  # Mock stackstac.stack
def test_build_raster_array(
    mock_stack: MagicMock,
    example_item: MagicMock,
    example_bbox: tuple[int, int, int, int],
    example_assets: list[str],
    example_epsg: int,
    example_resolution: tuple[float, float],
) -> None:
    # Create a mock xarray.DataArray to return from stackstac.stack
    mock_dataarray = MagicMock(spec=xr.DataArray)
    mock_stack.return_value = mock_dataarray

    # Call the function
    result = build_raster_array(
        item=example_item,
        bbox=example_bbox,
        assets=example_assets,
        epsg=example_epsg,
        resolution=example_resolution,
    )

    # Check if stackstac.stack was called with correct parameters
    mock_stack.assert_called_once_with(
        example_item,
        assets=example_assets,
        chunksize=consts.compute.CHUNK_SIZE,
        bounds_latlon=example_bbox,
        epsg=example_epsg,
        resolution=example_resolution,
    )

    # Check if result is the squeezed xarray.DataArray
    assert result == mock_dataarray.squeeze()
