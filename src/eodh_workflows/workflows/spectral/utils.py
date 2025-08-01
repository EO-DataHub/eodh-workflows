from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
from matplotlib import pyplot as plt
from skimage.filters import threshold_otsu
from skimage.morphology import closing, dilation, disk, remove_small_holes, remove_small_objects

from eodh_workflows.consts.compute import EPS
from eodh_workflows.workflows.spectral.functional import ndmi

if TYPE_CHECKING:
    from pathlib import Path

    import xarray

SCL_WATER_CLASS = 6
NDMI_WATER_THRESHOLD = 0.2
NDWI_WATER_THRESHOLD = -0.15
ARD_CLEAR_PIXELS = 0
SCL_INVALID_PIXELS = [0, 1, 3, 8, 9, 10, 11]


def rescale(data: xarray.DataArray, scale: float = 1e-4, offset: float = -0.1) -> xarray.DataArray:
    return data * scale + offset


def resolve_rescale_params(collection_name: str, item_datetime: datetime) -> tuple[float, float]:
    if collection_name == "sentinel-2-l2a":  # EarthSearch AWS already uses rescale info in STAC metadata
        return 1, 0
    if collection_name == "sentinel2_ard":
        return 1e-4, 0
    # Rescale - keep in mind baseline change on 25th of Jan. 2022
    return (1e-4, -0.1) if item_datetime > datetime(2022, 1, 25, tzinfo=UTC) else (1e-4, 0)


def sentinel_water_mask_from_scl(scl_agg: xarray.DataArray) -> np.ndarray[Any, Any]:  # type: ignore[type-arg]
    return np.where(scl_agg == SCL_WATER_CLASS, 1, 0)


def ard_cloud_mask(cloud_agg: xarray.DataArray) -> np.ndarray[Any, Any]:
    return np.where(cloud_agg == ARD_CLEAR_PIXELS, 0, 1)


def ard_clear_pixels_mask(cloud_agg: xarray.DataArray) -> np.ndarray[Any, Any]:
    return np.where(cloud_agg == ARD_CLEAR_PIXELS, 1, 0)


def ndmi_water_mask(
    green: xarray.DataArray,
    swir16: xarray.DataArray,
    threshold: float = NDMI_WATER_THRESHOLD,
) -> np.ndarray[Any, Any]:
    ndmi_arr = ndmi(green_agg=green, swir_agg=swir16, crs=green.rio.crs)
    return np.where(ndmi_arr >= threshold, 1, 0)


def post_process_mask(
    binary_mask: np.ndarray[Any, Any],
    min_obj_size: int = 100,
    max_hole_size: int = 100,
    disk_radius: int = 2,
) -> np.ndarray[Any, Any]:
    clean_mask = remove_small_objects(binary_mask, min_size=min_obj_size)
    clean_mask = remove_small_holes(clean_mask, area_threshold=max_hole_size)
    struct_elem = disk(disk_radius)
    clean_mask = closing(clean_mask, struct_elem)
    return dilation(clean_mask, struct_elem)  # type: ignore[no-any-return]


def save_mask(arr: np.ndarray[Any, Any], out_fp: Path) -> None:
    plt.imshow(arr, cmap="gray", vmin=0, vmax=1, interpolation="nearest")
    plt.colorbar()
    plt.tight_layout()
    plt.axis("off")
    plt.savefig(out_fp, bbox_inches="tight")
    plt.close()


def save_index(arr: np.ndarray[Any, Any] | xarray.DataArray, out_fp: Path, vmin: float, vmax: float, cmap: str) -> None:
    plt.imshow(arr, vmin=vmin, vmax=vmax, cmap=cmap, interpolation="nearest")
    plt.colorbar()
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(out_fp, bbox_inches="tight")
    plt.close()


def ndwi_water_mask(
    green: xarray.DataArray,
    nir: xarray.DataArray,
    threshold: float = NDWI_WATER_THRESHOLD,
) -> np.ndarray[Any, Any]:
    ndwi_arr = (green - nir) / (green + nir + EPS)
    return np.where(ndwi_arr >= threshold, 1, 0)


def ratio_water_mask(
    blue_agg: xarray.DataArray, swir_agg: xarray.DataArray, threshold: float = 2.0
) -> np.ndarray[Any, Any]:
    ratio = blue_agg / swir_agg
    return np.where(ratio > threshold, 1, 0)


def water_mask_from_arr(raster_arr: xarray.DataArray, scale: float = 1.0, offset: float = 0.0) -> np.ndarray[Any, Any]:
    return (
        sentinel_water_mask_from_scl(raster_arr.sel(band="scl"))
        if "scl" in raster_arr.band
        else ratio_water_mask(
            blue_agg=rescale(raster_arr.sel(band="blue"), scale=scale, offset=offset),
            swir_agg=rescale(raster_arr.sel(band="swir16"), scale=scale, offset=offset),
        )
    )


def sentinel_cloud_mask_from_scl(scl_agg: xarray.DataArray) -> np.ndarray[Any, Any]:
    return np.where(scl_agg.isin(SCL_INVALID_PIXELS), 0, 1)


def cloud_mask_from_arr(raster_arr: xarray.DataArray) -> np.ndarray[Any, Any]:
    return (
        sentinel_cloud_mask_from_scl(raster_arr.sel(band="scl"))
        if "scl" in raster_arr.band
        else ard_cloud_mask(raster_arr.sel(band="cloud"))
    )


def threshold_arr_and_post_process_mask(
    arr: xarray.DataArray,
    a_min: int,
    a_max: int,
    op: Literal["ge", "gt", "le", "lt"],
) -> np.ndarray[Any, Any]:
    thresh = threshold_otsu(np.clip(np.nan_to_num(arr.to_numpy(), nan=0, neginf=0, posinf=0), a_min=a_min, a_max=a_max))
    if op == "ge":
        mask = np.where(arr >= thresh, 1, 0)
    elif op == "gt":
        mask = np.where(arr > thresh, 1, 0)
    elif op == "le":
        mask = np.where(arr <= thresh, 1, 0)
    elif op == "lt":
        mask = np.where(arr < thresh, 1, 0)
    else:
        msg = f"Unknown operator {op}"
        raise ValueError(msg)
    return post_process_mask(mask)


def raster_stats(data: xarray.DataArray) -> dict[str, float]:
    return {
        "minimum": data.min(skipna=True).item(),
        "maximum": np.nanmax(data).item(),
        "mean": data.mean(skipna=True).item(),
        "median": data.median(skipna=True).item(),
        "q01": data.quantile(0.01, skipna=True).item(),
        "q99": data.quantile(0.99, skipna=True).item(),
        "stddev": data.std(skipna=True).item(),
        "valid_percent": (np.isnan(data.data).sum() / np.prod(data.shape)).item(),
    }
