from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import rioxarray  # noqa: F401
import xarray as xr

from src.raster_utils.save import save_cog


@patch("src.raster_utils.save.Path.cwd")  # Mock Path.cwd
def test_save_cog_with_defaults(mock_cwd: MagicMock) -> None:
    # Mocking DataArray
    mock_data_array = MagicMock(spec=xr.DataArray)

    # Create mock for rio methods in the mocked DataArray
    mock_rio = mock_data_array.rio
    mock_rio.write_crs.return_value = mock_data_array

    # Set return value for Path.cwd
    mock_cwd.return_value = Path("/mocked_cwd")

    # Call the function
    result = save_cog(mock_data_array, "item123")

    # Check if write_crs was called with the correct EPSG
    mock_rio.write_crs.assert_called_once_with("EPSG:4326")

    # Check if to_raster was called with the correct arguments
    mock_rio.to_raster.assert_called_once_with(Path("/mocked_cwd/item123.tif"), driver="COG", windowed=True)

    # Verify the function returned the correct path
    assert result == Path("/mocked_cwd/item123.tif")


# Test for custom output directory and EPSG
def test_save_cog_with_custom_output_dir() -> None:
    # Mocking DataArray
    mock_data_array = MagicMock(spec=xr.DataArray)

    # Create mock for rio methods in the mocked DataArray
    mock_rio = mock_data_array.rio
    mock_rio.write_crs.return_value = mock_data_array

    # Custom output directory
    output_dir = Path("/custom/output_dir")

    # Call the function
    result = save_cog(mock_data_array, "item123", output_dir=output_dir, epsg=3857)

    # Check if write_crs was called with the correct EPSG
    mock_rio.write_crs.assert_called_once_with("EPSG:3857")

    # Check if to_raster was called with the correct arguments
    mock_rio.to_raster.assert_called_once_with(Path("/custom/output_dir/item123.tif"), driver="COG", windowed=True)

    # Verify the function returned the correct path
    assert result == Path("/custom/output_dir/item123.tif")
