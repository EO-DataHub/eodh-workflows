from __future__ import annotations

import abc
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import numpy as np
import xarray
from skimage.morphology import closing, erosion, footprint_rectangle
from xrspatial.multispectral import evi, ndvi, savi

from src.consts.compute import EPS
from src.utils.logging import get_logger
from src.workflows.ds.utils import prepare_data_array

if TYPE_CHECKING:
    import pystac
    from rasterio import CRS

_logger = get_logger(__name__)
SCL_WATER_CLASS = 6
SWM_THRESHOLD = 0.9

EARTH_SEARCH_AWS_ASSET_LOOKUP = {
    "aot": "AOT",
    "coastal": "B01",
    "blue": "B02",
    "green": "B03",
    "red": "B04",
    "rededge1": "B05",
    "rededge2": "B06",
    "rededge3": "B07",
    "nir": "B08",
    "nir08": "B8A",
    "nir09": "B09",
    "swir16": "B11",
    "swir22": "B12",
    "scl": "SCL",
}


def rescale(data: xarray.DataArray, scale: float = 1e-4, offset: float = -0.1) -> xarray.DataArray:
    return data * scale + offset


def sentinel_water_mask_from_scl(scl_agg: xarray.DataArray) -> np.ndarray:  # type: ignore[type-arg]
    return np.where(scl_agg == SCL_WATER_CLASS, 1, 0)


def sentinel_water_mask_from_bands(
    blue: xarray.DataArray,
    green: xarray.DataArray,
    nir: xarray.DataArray,
    swir16: xarray.DataArray,
    threshold: float = SWM_THRESHOLD,
) -> np.ndarray[Any, Any]:
    """SWM from bands.

    Notes:
        The data should not be rescaled.

    """
    swm = (blue + green) / (nir + swir16)
    swm = np.where(swm >= threshold, 1, 0)
    swm = closing(swm, footprint_rectangle((5, 5)))
    return erosion(swm, footprint_rectangle((2, 2)))  # type: ignore[no-any-return]


def water_mask_from_arr(raster_arr: xarray.DataArray) -> np.ndarray[Any, Any]:
    return (
        sentinel_water_mask_from_scl(raster_arr.sel(band="scl"))
        if "scl" in raster_arr.band
        else sentinel_water_mask_from_bands(
            blue=raster_arr.sel(band="blue"),
            green=raster_arr.sel(band="green"),
            nir=raster_arr.sel(band="nir"),
            swir16=raster_arr.sel(band="swir16"),
        )
    )


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


def cya_cells_ml(
    blue_agg: xarray.DataArray,
    green_agg: xarray.DataArray,
    red_agg: xarray.DataArray,
    water_mask: np.ndarray,  # type: ignore[type-arg]
    crs: int | str | CRS,
) -> xarray.DataArray:
    """Calculates Cyanobacteria in 1e6 of cells / mL.

    Notes:
        Computed index range: 0.1 - 300.0 1e6 cells / mL.

    References:
        Potes et al. 2018.

    Arguments:
        blue_agg: Blue band (Sentinel-2 B02) data array with reflectance data.
        green_agg: Green band (Sentinel-2 B03) data array with reflectance data.
        red_agg: Red band (Sentinel-2 B04) data array with reflectance data.
        water_mask: Water mask to mask out land and clouds.
        crs: CRS to write to the output array.

    Returns:
        Data array with Cyanobacteria in 1e6 cells / mL.

    """
    data = 115_530.31 * ((green_agg * red_agg / (blue_agg + EPS)) ** 2.38)
    result_arr = xarray.DataArray(
        data,
        name="cya",
        coords=red_agg.coords,
        dims=red_agg.dims,
        attrs=red_agg.attrs,
    )
    return result_arr.where(water_mask).rio.write_crs(crs)


def cya_mg_m3(
    red_agg: xarray.DataArray,
    red_edge_agg: xarray.DataArray,
    water_mask: np.ndarray,  # type: ignore[type-arg]
    crs: int | str | CRS,
) -> xarray.DataArray:
    """Calculates Cyanobacteria in mg / m3.

    Notes:
        Computed index range: 0.13 - 1000 mg / m3.

    References:
        Soria-Perpinya et al. 2021.

    Arguments:
        red_agg: Red band (Sentinel-2 B04) data array with reflectance data.
        red_edge_agg: Red band (Sentinel-2 B05) data array with reflectance data.
        water_mask: Water mask to mask out land and clouds.
        crs: CRS to write to the output array.

    Returns:
        Data array with Cyanobacteria in mg / m3.

    """
    data = 21.554 * ((red_edge_agg / (red_agg + EPS)) ** 3.4791)
    result_arr = xarray.DataArray(
        data,
        name="cya",
        coords=red_agg.coords,
        dims=red_agg.dims,
        attrs=red_agg.attrs,
    )
    return result_arr.where(water_mask).rio.write_crs(crs)


def chl_a_high(
    red_agg: xarray.DataArray,
    red_edge_agg: xarray.DataArray,
    water_mask: np.ndarray,  # type: ignore[type-arg]
    crs: int | str | CRS,
) -> xarray.DataArray:
    """Calculates Chlorophyll-Alpha for high values > 5 mg / m3.

    Notes:
        Computed index range: 5.16 - 674.7 mg / m3.

    References:
        Soria-Perpinya et al. 2021.

    Arguments:
        red_agg: Red band (Sentinel-2 B04) data array with reflectance data.
        red_edge_agg: Red band (Sentinel-2 B05) data array with reflectance data.
        water_mask: Water mask to mask out land and clouds.
        crs: CRS to write to the output array.

    Returns:
        Data array with Chl-a in mg / m3.

    """
    data = 19.866 * ((red_edge_agg / (red_agg + EPS)) ** 2.3051)
    result_arr = xarray.DataArray(
        data,
        name="chl-a-high",
        coords=red_edge_agg.coords,
        dims=red_edge_agg.dims,
        attrs=red_edge_agg.attrs,
    )
    return result_arr.where(water_mask).rio.write_crs(crs)


def chl_a_low(
    blue_agg: xarray.DataArray,
    green_agg: xarray.DataArray,
    water_mask: np.ndarray,  # type: ignore[type-arg]
    crs: int | str | CRS,
) -> xarray.DataArray:
    """Calculates Chlorophyll-Alpha for low values < 5 mg / m3.

    Notes:
        Computed index range: 0.53 - 4.92 mg / m3.

    References:
        Soria-Perpinya et al. 2021.

    Arguments:
        blue_agg: Blue band (Sentinel-2 B02) data array with reflectance data.
        green_agg: Green band (Sentinel-2 B03) data array with reflectance data.
        water_mask: Water mask to mask out land and clouds.
        crs: CRS to write to the output array.

    Returns:
        Data array with Chl-a in mg / m3.

    """
    data = np.exp(-2.4792 * (np.log10(np.maximum(green_agg, blue_agg) / (green_agg + EPS))) - 0.0389)
    result_arr = xarray.DataArray(
        data,
        name="chl-a-low",
        coords=blue_agg.coords,
        dims=blue_agg.dims,
        attrs=blue_agg.attrs,
    )
    return result_arr.where(water_mask).rio.write_crs(crs)


def chl_a_coastal(
    red_agg: xarray.DataArray,
    red_edge_agg: xarray.DataArray,
    water_mask: np.ndarray,  # type: ignore[type-arg]
    crs: int | str | CRS,
) -> xarray.DataArray:
    """Calculates Chlorophyll-Alpha for coastal areas based on NDCI in mg / m3.

    Notes:
        Computed index range: 0.9 - 28.1 mg / m3.

    References:
        Mishra et al. 2012.

    Arguments:
        red_agg: Red band (Sentinel-2 B04) data array with reflectance data.
        red_edge_agg: Red Edge band (Sentinel-2 B05) data array with reflectance data.
        water_mask: Water mask to mask out land and clouds.
        crs: CRS to write to the output array.

    Returns:
        Data array with Chl-a in mg / m3.

    """
    data = (
        14.039
        + 86.11 * (red_edge_agg - red_agg) / ((red_agg + red_edge_agg) + EPS)
        + 194.325 * (red_edge_agg - red_agg) / ((red_edge_agg + red_agg) ** 2 + EPS)
    )
    data = np.maximum(data, 0)
    result_arr = xarray.DataArray(
        data,
        name="chl-a-coastal",
        coords=red_agg.coords,
        dims=red_agg.dims,
        attrs=red_agg.attrs,
    )
    return result_arr.where(water_mask).rio.write_crs(crs)


def turb(
    blue_agg: xarray.DataArray,
    red_edge_agg: xarray.DataArray,
    water_mask: np.ndarray,  # type: ignore[type-arg]
    crs: int | str | CRS,
) -> xarray.DataArray:
    """Water Turbidity index in NTU.

    Notes:
        Computed index range: 15 - 1000 NTU.

    References:
        Zhan et al. 2022

    Args:
        blue_agg: Blue band (Sentinel-2 B02) data array with reflectance data.
        red_edge_agg: Red edge band (Sentinel-2 B05) data array with reflectance data.
        water_mask: Water mask to mask out land and clouds.
        crs: CRS to write to the output array.

    Returns:
        Data array with Turbidity in NTU.

    """
    data = 194.79 * (red_edge_agg * (red_edge_agg / (blue_agg + EPS))) + 0.9061
    result_arr = xarray.DataArray(
        data,
        name="turb",
        coords=red_edge_agg.coords,
        dims=red_edge_agg.dims,
        attrs=red_edge_agg.attrs,
    )
    return result_arr.where(water_mask).rio.write_crs(crs)


def cdom(
    blue_agg: xarray.DataArray,
    red_agg: xarray.DataArray,
    water_mask: np.ndarray,  # type: ignore[type-arg]
    crs: int | str | CRS,
) -> xarray.DataArray:
    """Colored Dissolved Organic Matter index - CDOM in ug / L.

    Notes:
        Computed index range: 0.03 - 5.3 ug / L.

    References:
        Soria-Perpinya et al. 2021.

    Args:
        blue_agg: Blue band (Sentinel-2 B02) data array with reflectance data.
        red_agg: Red band (Sentinel-2 B04) data array with reflectance data.
        water_mask: Water mask to mask out land and clouds.
        crs: CRS to write to the output array.

    Returns:
        CDOM in ug / L.
    """
    data = 2.4072 * (red_agg / (blue_agg + EPS)) + 0.0709
    result_arr = xarray.DataArray(
        data,
        name="cdom",
        coords=blue_agg.coords,
        dims=blue_agg.dims,
        attrs=blue_agg.attrs,
    )
    return result_arr.where(water_mask).rio.write_crs(crs)


def doc(
    green_agg: xarray.DataArray,
    red_agg: xarray.DataArray,
    water_mask: np.ndarray,  # type: ignore[type-arg]
    crs: int | str | CRS,
) -> xarray.DataArray:
    """Dissolved Organic Carbon index - DOC in mg / L.

    Notes:
        Computed index range: 0.0 - 100.0 mg / L.

    References:
        Potes et al., 2018

    Args:
        green_agg: Red band (Sentinel-2 B03) data array with reflectance data.
        red_agg: Red band (Sentinel-2 B04) data array with reflectance data.
        water_mask: Water mask to mask out land and clouds.
        crs: CRS to write to the output array.

    Returns:
        DOC in mg / L.
    """
    data = 432 * np.exp(-2.24 * (green_agg / (red_agg + EPS)) + EPS)
    result_arr = xarray.DataArray(
        data,
        name="doc",
        coords=red_agg.coords,
        dims=red_agg.dims,
        attrs=red_agg.attrs,
    )
    return result_arr.where(water_mask).rio.write_crs(crs)


def resolve_rescale_params(collection_name: str, item_datetime: datetime) -> tuple[float, float]:
    if collection_name != "sentinel-2-l2a":  # EarthSearch AWS already uses rescale info in STAC metadata
        return 1, 0
    # Rescale - keep in mind baseline change on 25th of Jan. 2022
    return (1e-4, -0.1) if item_datetime > datetime(2022, 1, 25, tzinfo=timezone.utc) else (1e-4, 0)


class IndexCalculator(abc.ABC):
    @property
    @abc.abstractmethod
    def name(self) -> str: ...

    @property
    @abc.abstractmethod
    def full_name(self) -> str: ...

    @property
    @abc.abstractmethod
    def typical_range(self) -> tuple[float, float, int]:
        """Typical range for the index.

        Returns:
            A tuple with min, max, number_of_intervals

        """
        ...

    @property
    @abc.abstractmethod
    def units(self) -> str: ...

    @property
    @abc.abstractmethod
    def mpl_colormap(self) -> tuple[str, bool]: ...

    @property
    @abc.abstractmethod
    def js_colormap(self) -> tuple[str, bool]: ...

    @staticmethod
    @abc.abstractmethod
    def collection_assets_to_use(item: pystac.Item) -> list[str]: ...

    @property
    def raster_colormap(self) -> dict[str, Any]:
        vmin, vmax, intervals = self.typical_range
        js_cmap, cmap_reversed = self.js_colormap
        return {
            "name": js_cmap,
            "reversed": cmap_reversed,
            "min": vmin,
            "max": vmax,
            "steps": intervals,
            "units": self.units,
            "mpl_equivalent_cmap": self.mpl_colormap[0],
        }

    @property
    def raster_bands(self) -> list[dict[str, Any]]:
        return [
            {
                "nodata": np.nan,
                "unit": self.units,
            }
        ]

    def asset_extra_fields(self, index_raster: xarray.DataArray) -> dict[str, Any]:
        return {
            "colormap": self.raster_colormap,
            "statistics": raster_stats(index_raster),
            "raster:bands": self.raster_bands,
            "proj:shape": index_raster.shape,
            "proj:transform": list(index_raster.rio.transform()),
            "proj:epsg": index_raster.rio.crs.to_epsg(),
        }

    @staticmethod
    @abc.abstractmethod
    def calculate_index(
        raster_arr: xarray.DataArray,
        rescale_factor: float = 1e-4,
        rescale_offset: float = -0.1,
    ) -> xarray.DataArray: ...

    def compute(
        self,
        item: pystac.Item,
        bbox: tuple[float, float, float, float] | None = None,
    ) -> xarray.DataArray:
        raster_arr = prepare_data_array(item=item, bbox=bbox, assets=self.collection_assets_to_use(item))
        scale, offset = resolve_rescale_params(collection_name=item.collection_id, item_datetime=item.datetime)
        return self.calculate_index(raster_arr, scale, offset)


class NDVI(IndexCalculator):
    @property
    def name(self) -> str:
        return "ndvi"

    @property
    def full_name(self) -> str:
        return "Normalized Difference Vegetation Index (NDVI)"

    @property
    def typical_range(self) -> tuple[float, float, int]:
        return -1.0, 1.0, 20

    @property
    def units(self) -> str:
        return "NDVI"

    @property
    def mpl_colormap(self) -> tuple[str, bool]:
        return "YlGn", False

    @property
    def js_colormap(self) -> tuple[str, bool]:
        return "velocity-green", True

    @staticmethod
    def collection_assets_to_use(item: pystac.Item) -> list[str]:  # noqa: ARG004
        return ["red", "nir"]

    @staticmethod
    def calculate_index(
        raster_arr: xarray.DataArray,
        rescale_factor: float = 1e-4,
        rescale_offset: float = -0.1,
    ) -> xarray.DataArray:
        nir = rescale(raster_arr.sel(band="nir"), scale=rescale_factor, offset=rescale_offset)
        red = rescale(raster_arr.sel(band="red"), scale=rescale_factor, offset=rescale_offset)
        return ndvi(nir_agg=nir, red_agg=red).rio.write_crs(raster_arr.rio.crs)


class NDWI(IndexCalculator):
    @property
    def name(self) -> str:
        return "ndwi"

    @property
    def full_name(self) -> str:
        return "Normalized Difference Water Index (NDWI)"

    @property
    def typical_range(self) -> tuple[float, float, int]:
        return -1.0, 1.0, 20

    @property
    def units(self) -> str:
        return "NDWI"

    @property
    def mpl_colormap(self) -> tuple[str, bool]:
        return "RdBu", False

    @property
    def js_colormap(self) -> tuple[str, bool]:
        return "RdBu", False

    @staticmethod
    def collection_assets_to_use(item: pystac.Item) -> list[str]:  # noqa: ARG004
        return ["green", "nir"]

    @staticmethod
    def calculate_index(
        raster_arr: xarray.DataArray,
        rescale_factor: float = 1e-4,
        rescale_offset: float = -0.1,
    ) -> xarray.DataArray:
        nir = rescale(raster_arr.sel(band="nir"), scale=rescale_factor, offset=rescale_offset)
        green = rescale(raster_arr.sel(band="green"), scale=rescale_factor, offset=rescale_offset)
        return ndvi(nir_agg=green, red_agg=nir, name="ndwi").rio.write_crs(raster_arr.rio.crs)


class SAVI(IndexCalculator):
    @property
    def name(self) -> str:
        return "savi"

    @property
    def full_name(self) -> str:
        return "Soil Adjusted Vegetation Index (SAVI)"

    @property
    def typical_range(self) -> tuple[float, float, int]:
        return -1.0, 1.0, 20

    @property
    def units(self) -> str:
        return "SAVI"

    @property
    def mpl_colormap(self) -> tuple[str, bool]:
        return "YlGn", False

    @property
    def js_colormap(self) -> tuple[str, bool]:
        return "velocity-green", True

    @staticmethod
    def collection_assets_to_use(item: pystac.Item) -> list[str]:  # noqa: ARG004
        return ["red", "nir"]

    @staticmethod
    def calculate_index(
        raster_arr: xarray.DataArray,
        rescale_factor: float = 1e-4,
        rescale_offset: float = -0.1,
    ) -> xarray.DataArray:
        nir = rescale(raster_arr.sel(band="nir"), scale=rescale_factor, offset=rescale_offset)
        red = rescale(raster_arr.sel(band="red"), scale=rescale_factor, offset=rescale_offset)
        return savi(nir_agg=nir, red_agg=red).rio.write_crs(raster_arr.rio.crs)


class EVI(IndexCalculator):
    @property
    def name(self) -> str:
        return "evi"

    @property
    def full_name(self) -> str:
        return "Enhanced Vegetation Index (EVI)"

    @property
    def typical_range(self) -> tuple[float, float, int]:
        return -1.0, 1.0, 20

    @property
    def units(self) -> str:
        return "EVI"

    @property
    def mpl_colormap(self) -> tuple[str, bool]:
        return "YlGn", False

    @property
    def js_colormap(self) -> tuple[str, bool]:
        return "velocity-green", True

    @staticmethod
    def collection_assets_to_use(item: pystac.Item) -> list[str]:  # noqa: ARG004
        return ["blue", "red", "nir"]

    @staticmethod
    def calculate_index(
        raster_arr: xarray.DataArray,
        rescale_factor: float = 1e-4,
        rescale_offset: float = -0.1,
    ) -> xarray.DataArray:
        nir = rescale(raster_arr.sel(band="nir"), scale=rescale_factor, offset=rescale_offset)
        red = rescale(raster_arr.sel(band="red"), scale=rescale_factor, offset=rescale_offset)
        blue = rescale(raster_arr.sel(band="blue"), scale=rescale_factor, offset=rescale_offset)
        return evi(nir_agg=nir, red_agg=red, blue_agg=blue).rio.write_crs(raster_arr.rio.crs)


class CyaCells(IndexCalculator):
    @property
    def name(self) -> str:
        return "cya_cells"

    @property
    def full_name(self) -> str:
        return "Cyanobacteria Density (CYA)"

    @property
    def typical_range(self) -> tuple[float, float, int]:
        return 0.1, 300.0, 20

    @property
    def units(self) -> str:
        return "1e6 cells / mL"

    @property
    def mpl_colormap(self) -> tuple[str, bool]:
        return "jet", False

    @property
    def js_colormap(self) -> tuple[str, bool]:
        return "jet", False

    @staticmethod
    def collection_assets_to_use(item: pystac.Item) -> list[str]:
        return ["blue", "green", "red", "scl"] if "scl" in item.assets else ["blue", "green", "nir", "swir16"]

    @staticmethod
    def calculate_index(
        raster_arr: xarray.DataArray,
        rescale_factor: float = 1e-4,
        rescale_offset: float = -0.1,
    ) -> xarray.DataArray:
        water_mask = water_mask_from_arr(raster_arr)
        idx = cya_cells_ml(
            blue_agg=rescale(raster_arr.sel(band="blue"), scale=rescale_factor, offset=rescale_offset),
            green_agg=rescale(raster_arr.sel(band="green"), scale=rescale_factor, offset=rescale_offset),
            red_agg=rescale(raster_arr.sel(band="red"), scale=rescale_factor, offset=rescale_offset),
            water_mask=water_mask,
            crs=raster_arr.rio.crs,
        )
        return idx.where(np.isfinite(idx), np.nan)


class CyaMg(IndexCalculator):
    @property
    def name(self) -> str:
        return "cya_mg"

    @property
    def full_name(self) -> str:
        return "Cyanobacteria Density (CYA)"

    @property
    def typical_range(self) -> tuple[float, float, int]:
        return 0.13, 1000, 20

    @property
    def units(self) -> str:
        return "mg / m3"

    @property
    def mpl_colormap(self) -> tuple[str, bool]:
        return "jet", False

    @property
    def js_colormap(self) -> tuple[str, bool]:
        return "jet", False

    @staticmethod
    def collection_assets_to_use(item: pystac.Item) -> list[str]:
        return (
            ["red", "rededge1", "scl"]
            if "scl" in item.assets
            else ["blue", "green", "red", "rededge1", "nir", "swir16"]
        )

    @staticmethod
    def calculate_index(
        raster_arr: xarray.DataArray,
        rescale_factor: float = 1e-4,
        rescale_offset: float = -0.1,
    ) -> xarray.DataArray:
        water_mask = water_mask_from_arr(raster_arr)
        idx = cya_mg_m3(
            red_agg=rescale(raster_arr.sel(band="red"), scale=rescale_factor, offset=rescale_offset),
            red_edge_agg=rescale(raster_arr.sel(band="rededge1"), scale=rescale_factor, offset=rescale_offset),
            water_mask=water_mask,
            crs=raster_arr.rio.crs,
        )
        return idx.where(np.isfinite(idx), np.nan)


class ChlACoastal(IndexCalculator):
    @property
    def name(self) -> str:
        return "chl_a_coastal"

    @property
    def full_name(self) -> str:
        return "Chlorophyll A (for coastal regions) (ChlA)"

    @property
    def typical_range(self) -> tuple[float, float, int]:
        return 0.9, 28.1, 20

    @property
    def units(self) -> str:
        return "mg / m3"

    @property
    def mpl_colormap(self) -> tuple[str, bool]:
        return "jet", False

    @property
    def js_colormap(self) -> tuple[str, bool]:
        return "jet", False

    @staticmethod
    def collection_assets_to_use(item: pystac.Item) -> list[str]:
        return (
            ["red", "rededge1", "scl"]
            if "scl" in item.assets
            else ["blue", "green", "red", "rededge1", "nir", "swir16"]
        )

    @staticmethod
    def calculate_index(
        raster_arr: xarray.DataArray,
        rescale_factor: float = 1e-4,
        rescale_offset: float = -0.1,
    ) -> xarray.DataArray:
        water_mask = water_mask_from_arr(raster_arr)
        idx = chl_a_coastal(
            red_agg=rescale(raster_arr.sel(band="red"), scale=rescale_factor, offset=rescale_offset),
            red_edge_agg=rescale(raster_arr.sel(band="rededge1"), scale=rescale_factor, offset=rescale_offset),
            water_mask=water_mask,
            crs=raster_arr.rio.crs,
        )
        return idx.where(np.isfinite(idx), np.nan)


class ChlALow(IndexCalculator):
    @property
    def name(self) -> str:
        return "chl_a_low"

    @property
    def full_name(self) -> str:
        return "Chlorophyll A (for low values) (ChlA)"

    @property
    def typical_range(self) -> tuple[float, float, int]:
        return 0.53, 4.92, 20

    @property
    def units(self) -> str:
        return "mg / m3"

    @property
    def mpl_colormap(self) -> tuple[str, bool]:
        return "jet", False

    @property
    def js_colormap(self) -> tuple[str, bool]:
        return "jet", False

    @staticmethod
    def collection_assets_to_use(item: pystac.Item) -> list[str]:
        return ["blue", "green", "scl"] if "scl" in item.assets else ["blue", "green", "nir", "swir16"]

    @staticmethod
    def calculate_index(
        raster_arr: xarray.DataArray,
        rescale_factor: float = 1e-4,
        rescale_offset: float = -0.1,
    ) -> xarray.DataArray:
        water_mask = (
            sentinel_water_mask_from_scl(raster_arr.sel(band="scl"))
            if "scl" in raster_arr.band
            else sentinel_water_mask_from_bands(
                blue=raster_arr.sel(band="blue"),
                green=raster_arr.sel(band="green"),
                nir=raster_arr.sel(band="nir"),
                swir16=raster_arr.sel(band="swir16"),
            )
        )
        idx = chl_a_low(
            blue_agg=rescale(raster_arr.sel(band="blue"), scale=rescale_factor, offset=rescale_offset),
            green_agg=rescale(raster_arr.sel(band="green"), scale=rescale_factor, offset=rescale_offset),
            water_mask=water_mask,
            crs=raster_arr.rio.crs,
        )
        return idx.where(np.isfinite(idx), np.nan)


class ChlAHigh(IndexCalculator):
    @property
    def name(self) -> str:
        return "chl_a_high"

    @property
    def full_name(self) -> str:
        return "Chlorophyll A (for high values) (ChlA)"

    @property
    def typical_range(self) -> tuple[float, float, int]:
        return 5.16, 674.7, 20

    @property
    def units(self) -> str:
        return "mg / m3"

    @property
    def mpl_colormap(self) -> tuple[str, bool]:
        return "jet", False

    @property
    def js_colormap(self) -> tuple[str, bool]:
        return "jet", False

    @staticmethod
    def collection_assets_to_use(item: pystac.Item) -> list[str]:
        return (
            ["red", "rededge1", "scl"]
            if "scl" in item.assets
            else ["blue", "green", "red", "rededge1", "nir", "swir16"]
        )

    @staticmethod
    def calculate_index(
        raster_arr: xarray.DataArray,
        rescale_factor: float = 1e-4,
        rescale_offset: float = -0.1,
    ) -> xarray.DataArray:
        water_mask = water_mask_from_arr(raster_arr)
        idx = chl_a_high(
            red_agg=rescale(raster_arr.sel(band="red"), scale=rescale_factor, offset=rescale_offset),
            red_edge_agg=rescale(raster_arr.sel(band="rededge1"), scale=rescale_factor, offset=rescale_offset),
            water_mask=water_mask,
            crs=raster_arr.rio.crs,
        )
        return idx.where(np.isfinite(idx), np.nan)


class Turbidity(IndexCalculator):
    @property
    def name(self) -> str:
        return "turb"

    @property
    def full_name(self) -> str:
        return "Turbidity (TURB)"

    @property
    def typical_range(self) -> tuple[float, float, int]:
        return 15, 1000, 20

    @property
    def units(self) -> str:
        return "NTU"

    @property
    def mpl_colormap(self) -> tuple[str, bool]:
        return "jet", False

    @property
    def js_colormap(self) -> tuple[str, bool]:
        return "jet", False

    @staticmethod
    def collection_assets_to_use(item: pystac.Item) -> list[str]:
        return ["blue", "rededge1", "scl"] if "scl" in item.assets else ["blue", "green", "rededge1", "nir", "swir16"]

    @staticmethod
    def calculate_index(
        raster_arr: xarray.DataArray,
        rescale_factor: float = 1e-4,
        rescale_offset: float = -0.1,
    ) -> xarray.DataArray:
        water_mask = water_mask_from_arr(raster_arr)
        idx = turb(
            blue_agg=rescale(raster_arr.sel(band="blue"), scale=rescale_factor, offset=rescale_offset),
            red_edge_agg=rescale(raster_arr.sel(band="rededge1"), scale=rescale_factor, offset=rescale_offset),
            water_mask=water_mask,
            crs=raster_arr.rio.crs,
        )
        return idx.where(np.isfinite(idx), np.nan)


class DOC(IndexCalculator):
    @property
    def name(self) -> str:
        return "doc"

    @property
    def full_name(self) -> str:
        return "Dissolved Organic Carbon (DOC)"

    @property
    def typical_range(self) -> tuple[float, float, int]:
        return 0.0, 100.0, 20

    @property
    def units(self) -> str:
        return "mg / m3"

    @property
    def mpl_colormap(self) -> tuple[str, bool]:
        return "jet", False

    @property
    def js_colormap(self) -> tuple[str, bool]:
        return "jet", False

    @staticmethod
    def collection_assets_to_use(item: pystac.Item) -> list[str]:
        return ["green", "red", "scl"] if "scl" in item.assets else ["blue", "green", "red", "nir", "swir16"]

    @staticmethod
    def calculate_index(
        raster_arr: xarray.DataArray,
        rescale_factor: float = 1e-4,
        rescale_offset: float = -0.1,
    ) -> xarray.DataArray:
        water_mask = water_mask_from_arr(raster_arr)
        idx = doc(
            green_agg=rescale(raster_arr.sel(band="green"), scale=rescale_factor, offset=rescale_offset),
            red_agg=rescale(raster_arr.sel(band="red"), scale=rescale_factor, offset=rescale_offset),
            water_mask=water_mask,
            crs=raster_arr.rio.crs,
        )
        return idx.where(np.isfinite(idx), np.nan)


class CDOM(IndexCalculator):
    @property
    def name(self) -> str:
        return "cdom"

    @property
    def full_name(self) -> str:
        return "Colored Dissolved Organic Matter (CDOM)"

    @property
    def typical_range(self) -> tuple[float, float, int]:
        return 0.03, 5.3, 20

    @property
    def units(self) -> str:
        return "ug / L"

    @property
    def mpl_colormap(self) -> tuple[str, bool]:
        return "jet", False

    @property
    def js_colormap(self) -> tuple[str, bool]:
        return "jet", False

    @staticmethod
    def collection_assets_to_use(item: pystac.Item) -> list[str]:
        return ["blue", "red", "scl"] if "scl" in item.assets else ["blue", "green", "red", "nir", "swir16"]

    @staticmethod
    def calculate_index(
        raster_arr: xarray.DataArray,
        rescale_factor: float = 1e-4,
        rescale_offset: float = -0.1,
    ) -> xarray.DataArray:
        water_mask = water_mask_from_arr(raster_arr)
        idx = cdom(
            blue_agg=rescale(raster_arr.sel(band="blue"), scale=rescale_factor, offset=rescale_offset),
            red_agg=rescale(raster_arr.sel(band="red"), scale=rescale_factor, offset=rescale_offset),
            water_mask=water_mask,
            crs=raster_arr.rio.crs,
        )
        return idx.where(np.isfinite(idx), np.nan)


_SPECTRAL_INDEX_CLS: set[type[IndexCalculator]] = {
    NDVI,
    NDWI,
    EVI,
    SAVI,
    CyaCells,
    CyaMg,
    Turbidity,
    ChlACoastal,
    ChlALow,
    ChlAHigh,
    CDOM,
    DOC,
}
SPECTRAL_INDICES = {cls().name: cls() for cls in _SPECTRAL_INDEX_CLS}
