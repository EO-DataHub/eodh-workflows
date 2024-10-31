from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import xarray as xr
from pystac import Item

from src import consts
from src.raster_utils.build import build_raster_array
from src.workflows.lulc.generate_change import DATASOURCE_LOOKUP, DataSource


@pytest.fixture
def example_item() -> MagicMock:
    # Create a mock pystac.Item or use a real one for testing
    item = MagicMock(spec=Item)
    item.properties = {"geospatial_lon_resolution": "0.0001", "geospatial_lat_resolution": "0.0001"}
    item.id = "example-item-id"
    return item


@pytest.fixture
def example_bbox() -> tuple[int, int, int, int]:
    return (0, 0, 1, 1)


@pytest.fixture
def example_source_ceda() -> DataSource:
    return DATASOURCE_LOOKUP[consts.stac.CEDA_ESACCI_LC_LOCAL_NAME]


@pytest.fixture
def example_source_sh() -> DataSource:
    return DATASOURCE_LOOKUP[consts.stac.SH_CLMS_CORINELC_LOCAL_NAME]


@patch("src.raster_utils.build.stackstac.stack")
def test_build_raster_array_ceda(
    mock_stack: MagicMock,
    example_source_ceda: DataSource,
    example_item: MagicMock,
    example_bbox: tuple[int, int, int, int],
) -> None:
    # Create a mock xarray.DataArray to return from stackstac.stack
    mock_dataarray = MagicMock(spec=xr.DataArray)
    mock_stack.return_value = mock_dataarray

    # Call the function
    result = build_raster_array(source=example_source_ceda, item=example_item, bbox=example_bbox)

    # Check if stackstac.stack was called with correct parameters
    mock_stack.assert_called_once_with(
        example_item,
        assets=["GeoTIFF"],
        chunksize=consts.compute.CHUNK_SIZE,
        bounds_latlon=example_bbox,
        epsg=4326,
        resolution=(0.0001, 0.0001),
    )

    # Check if result is the squeezed xarray.DataArray
    assert result == mock_dataarray.squeeze()


@patch("src.raster_utils.build.sh_get_data")
@patch("src.raster_utils.build.sh_auth_token")
def test_build_raster_array_sh(
    mock_sh_auth_token: MagicMock,
    mock_sh_get_data: MagicMock,
    example_source_sh: DataSource,
    example_item: MagicMock,
    example_bbox: tuple[int, int, int, int],
) -> None:
    # Create a mock xarray.DataArray to return from sh_get_data
    mock_dataarray = MagicMock(spec=xr.DataArray)
    mock_sh_get_data.return_value = mock_dataarray
    mock_sh_auth_token.return_value = "fake-token"

    # Call the function
    result = build_raster_array(source=example_source_sh, item=example_item, bbox=example_bbox)

    # Check if sh_auth_token was called
    mock_sh_auth_token.assert_called_once()

    # Check if sh_get_data was called with correct parameters
    mock_sh_get_data.assert_called_once_with(
        token="fake-token",  # noqa: S106
        source=example_source_sh,
        bbox=example_bbox,
        stac_collection=example_source_sh.collection,
        item_id=example_item.id,
    )

    # Check if result is the xarray.DataArray returned by sh_get_data
    assert result == mock_dataarray
