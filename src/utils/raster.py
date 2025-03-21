from __future__ import annotations

import base64
import math
from io import BytesIO
from typing import TYPE_CHECKING

import numpy as np
import rioxarray  # noqa: F401
import stackstac
from matplotlib import cm
from PIL import Image
from rasterio.enums import Resampling
from rasterio.features import shapes
from shapely import MultiPolygon, Polygon
from shapely.geometry import box, shape

from src import consts
from src.consts.compute import EPS
from src.consts.crs import PSEUDO_MERCATOR, WGS84
from src.core.settings import current_settings
from src.utils.logging import get_logger
from src.utils.sentinel_hub import sh_auth_token, sh_get_data

if TYPE_CHECKING:
    from pathlib import Path

    import xarray as xr
    from pystac import Item

    from src.workflows.legacy.lulc.helpers import DataSource

_logger = get_logger(__name__)

EXPECTED_NDIM = 2
settings = current_settings()


def build_raster_array(
    source: DataSource,
    item: Item,
    bbox: tuple[int | float, int | float, int | float, int | float],
    epsg: int = WGS84,
) -> xr.DataArray:
    if source.catalog.startswith(current_settings().eodh.stac_api_endpoint):
        return (
            stackstac.stack(
                item,
                assets=["GeoTIFF"],
                chunksize=consts.compute.CHUNK_SIZE,
                bounds_latlon=bbox,
                epsg=epsg,
                resolution=(
                    float(item.properties.get("geospatial_lon_resolution")),
                    float(item.properties.get("geospatial_lat_resolution")),
                ),
            )
            .squeeze()
            .compute()
        )
    if source.catalog == settings.sentinel_hub.stac_api_endpoint:
        return sh_get_data(
            token=sh_auth_token(),
            source=source,
            bbox=bbox,
            stac_collection=source.collection,
            item=item,
        )
    error_message = "Unsupported STAC catalog"
    raise ValueError(error_message)


def get_raster_bounds(xarr: xr.DataArray) -> Polygon:
    """Calculates bounds for the raster array."""
    bbox = xarr.rio.reproject(WGS84).rio.bounds() if xarr.rio.crs.to_epsg() != WGS84 else xarr.rio.bounds()
    return box(*bbox)


def get_raster_polygon(xarr: xr.DataArray) -> Polygon:
    # Mask NaNs (True where data is valid)
    valid_mask = ~np.isnan(xarr.values)

    # Extract valid geometries using rasterio.features.shapes
    transform = xarr.rio.transform()
    shapes_generator = shapes(valid_mask.astype(np.uint8), transform=transform)

    # Collect all polygons
    polygons = [shape(geom) for geom, value in shapes_generator if value == 1]

    if not polygons:
        error_message = "No valid data found to create a polygon."
        raise ValueError(error_message)

    # Combine polygons into a single geometry
    return polygons[0] if len(polygons) == 1 else MultiPolygon(polygons).union


def save_cog(arr: xr.DataArray, asset_id: str, output_dir: Path, epsg: int | None = None) -> Path:
    _logger.info("Saving '%s' COG to %s", asset_id, output_dir.as_posix())
    output_dir.mkdir(parents=True, exist_ok=True)

    if epsg is not None:
        arr = arr.rio.reproject(f"EPSG:{epsg}")

    arr.rio.to_raster(output_dir / f"{asset_id}.tif", driver="COG")

    return output_dir / f"{asset_id}.tif"


def save_cog_v2(arr: xr.DataArray, output_file_path: Path) -> Path:
    _logger.info("Saving '%s' COG to %s", output_file_path.name, output_file_path.as_posix())
    output_file_path.parent.mkdir(parents=True, exist_ok=True)

    if arr.rio.crs is None:
        _logger.warning("CRS on `rio` accessor for item '%s' was not set", output_file_path.as_posix())

    arr.rio.to_raster(output_file_path.as_posix(), driver="COG")

    return output_file_path


def _create_color_mapping(classes_list: list[dict[str, int | str]]) -> dict[int, str]:
    return {int(entry["value"]): str(entry["color-hint"]) for entry in classes_list}


def generate_thumbnail_with_discrete_classes(
    data: xr.DataArray,
    out_fp: Path,
    classes_list: list[dict[str, int | str]],
    thumbnail_size: int = 64,
    epsg: int = PSEUDO_MERCATOR,
) -> None:
    out_fp.parent.mkdir(parents=True, exist_ok=True)

    colors_dict = _create_color_mapping(classes_list=classes_list)

    # Assume the first band contains the land use values
    band_data = data[0] if data.ndim != EXPECTED_NDIM else data

    if band_data.rio.crs.to_epsg() != epsg:
        band_data = band_data.rio.reproject(f"EPSG:{epsg}")

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
    thumbnail.save(out_fp, "PNG")


def generate_thumbnail_with_continuous_colormap(
    data: xr.DataArray,
    out_fp: Path,
    colormap: str,
    thumbnail_size: int = 64,
    min_val: float = -1.0,
    max_val: float = 1.0,
    epsg: int = PSEUDO_MERCATOR,
) -> None:
    out_fp.parent.mkdir(parents=True, exist_ok=True)

    _logger.info("Generating thumbnail with continuous colormap")
    # Assume the first band contains the data
    band_data = data[0] if data.ndim != EXPECTED_NDIM else data

    if band_data.rio.crs.to_epsg() != epsg:
        band_data = band_data.rio.reproject(f"EPSG:{epsg}")

    # Get original dimensions
    height, width = band_data.shape

    # Calculate scaling factor to fit the longest axis to the thumbnail size
    scale_factor = thumbnail_size / max(width, height)
    new_width = math.ceil(width * scale_factor)
    new_height = math.ceil(height * scale_factor)

    # Resize the data using nearest-neighbor interpolation for categorical data
    resized_data = band_data.rio.reproject(
        band_data.rio.crs,
        shape=(new_height, new_width),
        resampling=Resampling.average,
    )

    # Convert resized data to a numpy array
    resized_array = resized_data.to_numpy()

    # Normalize array to be in range [0-1]
    resized_array = (resized_array - min_val) / (max_val - min_val + consts.compute.EPS)

    # Apply colormap
    mpl_colormap = cm.get_cmap(colormap)
    rgba_image = mpl_colormap(resized_array, bytes=True)

    # Handle NoData values (assume NoData is represented by np.nan or a specific value)
    nodata_value = data.rio.nodata
    if nodata_value is not None:
        rgba_image[np.where(resized_array == nodata_value)] = (0, 0, 0, 0)  # Transparent for NoData

    # Convert the numpy array to a PIL image
    thumbnail = Image.fromarray(rgba_image, mode="RGBA")

    # Save the thumbnail to a PNG file
    thumbnail.save(out_fp, "PNG")


def generate_thumbnail_as_grayscale_image(
    data: xr.DataArray,
    out_fp: Path,
    thumbnail_size: int = 64,
    epsg: int = PSEUDO_MERCATOR,
) -> None:
    out_fp.parent.mkdir(parents=True, exist_ok=True)

    # Reproject to the specified EPSG
    data_reprojected = data.rio.reproject(f"EPSG:{epsg}").squeeze()

    # Normalize the data to range 0-255 for image representation
    data_min = np.nanquantile(data_reprojected.values, 0.02)
    data_max = np.nanquantile(data_reprojected.values, 0.98)

    data_normalized = ((data_reprojected - data_min) / (data_max - data_min + EPS)) * 255
    data_normalized = data_normalized.clip(0, 255).astype(np.uint8)

    # Resize the DataArray to the specified thumbnail size
    height, width = data.shape[-2], data.shape[-1]

    # Calculate scaling factor to fit the longest axis to the thumbnail size
    scale_factor = thumbnail_size / max(width, height)
    new_width = math.ceil(width * scale_factor)
    new_height = math.ceil(height * scale_factor)

    # Use rasterio to resample the image
    data_resized = data_normalized.rio.reproject(
        data.rio.crs,
        shape=(new_width, new_height),
        resampling=Resampling.nearest,
    )

    # Convert the resized data to a PIL Image and save as PNG
    image = Image.fromarray(data_resized[0, :, :].data if len(data_resized.shape) == 3 else data_resized.data)  # noqa: PLR2004
    image.save(out_fp.with_suffix(".png"))


def generate_thumbnail_rgb(
    data: xr.DataArray,
    out_fp: Path,
    thumbnail_size: int = 64,
    epsg: int = PSEUDO_MERCATOR,
) -> None:
    # We assume the data is 3D raster of shape (channels, height, width)
    out_fp.parent.mkdir(parents=True, exist_ok=True)

    # Reproject to the specified EPSG
    data_reprojected = data.rio.reproject(f"EPSG:{epsg}").squeeze()

    # Resize the DataArray to the specified thumbnail size
    _, height, width = data.shape

    # Calculate scaling factor to fit the longest axis to the thumbnail size
    scale_factor = thumbnail_size / max(width, height)
    new_width = math.ceil(width * scale_factor)
    new_height = math.ceil(height * scale_factor)

    # Use rasterio to resample the image
    data_resized = data_reprojected.rio.reproject(
        data.rio.crs,
        shape=(new_width, new_height),
        resampling=Resampling.nearest,
    )

    # Convert the resized data to a PIL Image and save as PNG
    image = Image.fromarray(np.rollaxis(data_resized.values, 0, 3))
    image.save(out_fp.with_suffix(".png"))


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
