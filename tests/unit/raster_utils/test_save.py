from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import xarray as xr

from src.raster_utils.save import save_cog


def test_save_cog_with_defaults_no_reprojection() -> None:
    # Mocking DataArray
    mock_data_array = MagicMock(spec=xr.DataArray)

    # Mocking the rio attribute and its methods
    mock_rio = mock_data_array.rio
    mock_rio.crs.to_epsg.return_value = 4326  # Set EPSG to match the default EPSG, so no reprojection occurs
    mock_rio.write_crs.return_value = mock_data_array  # Mock that write_crs returns the DataArray itself

    # Call the function
    result = save_cog(mock_data_array, "item123")

    # Check if write_crs was called with the correct EPSG
    mock_rio.write_crs.assert_called_once_with("EPSG:4326")

    # Ensure reproject was not called since EPSG was the same
    mock_rio.reproject.assert_not_called()

    # Check if to_raster was called with the correct arguments
    mock_rio.to_raster.assert_called_once_with(
        Path.cwd() / "data" / "stac-catalog" / "item123.tif", driver="COG", windowed=True
    )

    # Verify the function returned the correct path
    assert result == Path.cwd() / "data" / "stac-catalog" / "item123.tif"


def test_save_cog_with_reprojection() -> None:
    # Mocking DataArray
    mock_data_array = MagicMock(spec=xr.DataArray)

    # Mocking the rio attribute and its methods
    mock_rio = mock_data_array.rio
    mock_rio.crs.to_epsg.return_value = 3857  # Set EPSG to a different value, so reprojection should occur
    mock_rio.reproject.return_value = mock_data_array  # Mock that reprojection returns the DataArray itself
    mock_rio.write_crs.return_value = mock_data_array  # Mock that write_crs returns the DataArray itself

    # Call the function
    result = save_cog(mock_data_array, "item123")

    # Check if reproject was called because EPSG was different
    mock_rio.reproject.assert_called_once_with("EPSG:4326")

    # Check if write_crs was called with the correct EPSG
    mock_rio.write_crs.assert_called_once_with("EPSG:4326")

    # Check if to_raster was called with the correct arguments
    mock_rio.to_raster.assert_called_once_with(
        Path.cwd() / "data" / "stac-catalog" / "item123.tif", driver="COG", windowed=True
    )

    # Verify the function returned the correct path
    assert result == Path.cwd() / "data" / "stac-catalog" / "item123.tif"


def test_save_cog_with_custom_output_dir_and_epsg() -> None:
    # Mocking DataArray
    mock_data_array = MagicMock(spec=xr.DataArray)

    # Mocking the rio attribute and its methods
    mock_rio = mock_data_array.rio
    mock_rio.crs.to_epsg.return_value = 4326  # Set EPSG to the default, no reprojection expected
    mock_rio.reproject.return_value = mock_data_array  # Mock that reprojection returns the DataArray itself
    mock_rio.write_crs.return_value = mock_data_array  # Mock that write_crs returns the DataArray itself

    # Custom output directory
    output_dir = Path("/custom/output_dir")

    # Call the function with a custom EPSG
    result = save_cog(mock_data_array, "item123", output_dir=output_dir, epsg=3857)

    # Check if write_crs was called with the correct EPSG
    mock_rio.reproject.assert_called_once_with("EPSG:3857")

    # Check if write_crs was called with the correct EPSG
    mock_rio.write_crs.assert_called_once_with("EPSG:3857")

    # Check if to_raster was called with the correct arguments
    mock_rio.to_raster.assert_called_once_with(Path("/custom/output_dir/item123.tif"), driver="COG", windowed=True)

    # Verify the function returned the correct path
    assert result == Path("/custom/output_dir/item123.tif")
