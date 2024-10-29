from __future__ import annotations

import base64
from io import BytesIO
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image
from rasterio.enums import Resampling

from src.local_stac.generate import LOCAL_STAC_OUTPUT_DIR

if TYPE_CHECKING:
    from pathlib import Path

    import xarray

# current scope doesn't require using multiple bands
EXPECTED_NDIM = 2

# output CRS for thumbnail
THUMBNAIL_CRS = 3857


def _create_color_mapping(classes_list: list[dict[str, int | str]]) -> dict[int, str]:
    return {int(entry["value"]): str(entry["color-hint"]) for entry in classes_list}


def generate_thumbnail(
    data: xarray.DataArray, raster_path: Path, classes_list: list[dict[str, int | str]], thumbnail_size: int = 256
) -> Path:
    colors_dict = _create_color_mapping(classes_list=classes_list)

    # Assume the first band contains the land use values
    band_data = data[0] if data.ndim != EXPECTED_NDIM else data

    if band_data.rio.crs.to_epsg() != THUMBNAIL_CRS:
        band_data = band_data.rio.reproject(f"EPSG:{THUMBNAIL_CRS}")

    # Get original dimensions
    height, width = band_data.shape

    # Calculate scaling factor to fit the longest axis to the thumbnail size
    scale_factor = thumbnail_size / max(width, height)
    new_width = int(width * scale_factor)
    new_height = int(height * scale_factor)

    # Resize the data using nearest-neighbor interpolation for categorical data
    resized_data = band_data.rio.reproject(band_data.rio.crs, shape=(new_height, new_width), resampling=Resampling.mode)

    # Convert resized data to a numpy array
    resized_array = resized_data.to_numpy()

    # Create an RGBA image from the land use values using the color map
    rgba_image = np.zeros((new_height, new_width, 4), dtype=np.uint8)
    for land_value, color_hex in colors_dict.items():
        # Convert hex color to RGB
        color_rgb = tuple(int(color_hex[i : i + 2], 16) for i in (0, 2, 4))
        rgba_image[np.where(resized_array == land_value)] = (*color_rgb, 255)  # Full opacity

    # Handle NoData values (assume NoData is represented by np.nan or a specific value)
    nodata_value = data.rio.nodata
    if nodata_value is not None:
        rgba_image[np.where(resized_array == nodata_value)] = (0, 0, 0, 0)  # Transparent for NoData

    # Convert the numpy array to a PIL image
    thumbnail = Image.fromarray(rgba_image, mode="RGBA")

    # Save the thumbnail to a PNG file
    output_png_path = LOCAL_STAC_OUTPUT_DIR / f"{raster_path.stem}.png"
    thumbnail.save(output_png_path, "PNG")
    return output_png_path


def image_to_base64(image_path: Path) -> str:
    # Open the image file
    with Image.open(image_path) as img:
        # Create a buffer to store the image in memory
        buffered = BytesIO()
        # Save the image as PNG to the buffer
        img.save(buffered, format="PNG")
        # Get the byte data from the buffer
        img_bytes = buffered.getvalue()
        # Encode the byte data to base64
        return base64.b64encode(img_bytes).decode("utf-8")
