from __future__ import annotations

import abc
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import numpy as np
import rioxarray  # noqa: F401
import stackstac
import xarray
from xrspatial.multispectral import evi, ndvi, savi

from src import consts
from src.consts.compute import EPS
from src.consts.crs import WGS84
from src.consts.stac import LOCAL_COLLECTION_NAME, SENTINEL_2_L2A_COLLECTION_NAME
from src.utils.logging import get_logger

if TYPE_CHECKING:
    import pystac
    from rasterio import CRS

_logger = get_logger(__name__)
SCL_WATER_CLASS = 6

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
PLANETARY_COMPUTER_ASSET_LOOKUP = {v: k for k, v in EARTH_SEARCH_AWS_ASSET_LOOKUP.items()}


def unify_asset_identifiers(assets_to_use: list[str], collection: str) -> list[str]:
    if collection in {SENTINEL_2_L2A_COLLECTION_NAME, LOCAL_COLLECTION_NAME}:
        return assets_to_use
    return [PLANETARY_COMPUTER_ASSET_LOOKUP[a] for a in assets_to_use]


def rescale(data: xarray.DataArray, scale: float = 1e-4, offset: float = -0.1) -> xarray.DataArray:
    return data * scale + offset


def sentinel_water_mask(scl_agg: xarray.DataArray) -> np.ndarray:  # type: ignore[type-arg]
    return np.where(scl_agg == SCL_WATER_CLASS, 1, 0)


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
    data = 432 * np.exp(-2.24 * (green_agg / (red_agg + EPS)))
    result_arr = xarray.DataArray(
        data,
        name="doc",
        coords=red_agg.coords,
        dims=red_agg.dims,
        attrs=red_agg.attrs,
    )
    return result_arr.where(water_mask).rio.write_crs(crs)


def prepare_data_array(
    item: pystac.Item, assets: list[str], bbox: tuple[float, float, float, float] | None = None
) -> xarray.DataArray:
    mapped_asset_ids = unify_asset_identifiers(assets_to_use=assets, collection=item.collection_id)
    return (
        (
            stackstac.stack(
                [item],
                assets=assets,
                chunksize=consts.compute.CHUNK_SIZE,
                bounds_latlon=bbox,
                epsg=WGS84,
            )
        )
        .assign_coords({"band": mapped_asset_ids})  # use common names
        .squeeze()
        .compute()
    )


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

    @property
    @abc.abstractmethod
    def collection_assets_to_use(self) -> dict[str, list[str]]: ...

    @staticmethod
    @abc.abstractmethod
    def calculate_index(
        raster_arr: xarray.DataArray,
        rescale_factor: float = 1e-5,
        rescale_offset: float = -0.1,
    ) -> xarray.DataArray: ...

    def compute(
        self,
        item: pystac.Item,
        bbox: tuple[float, float, float, float] | None = None,
    ) -> xarray.DataArray:
        raster_arr = prepare_data_array(item=item, bbox=bbox, assets=self.collection_assets_to_use[item.collection_id])
        scale, offset = resolve_rescale_params(collection_name=item.collection_id, item_datetime=item.datetime)
        return self.calculate_index(raster_arr, scale, offset)


class NDVI(IndexCalculator):
    @property
    def name(self) -> str:
        return "ndvi"

    @property
    def full_name(self) -> str:
        return "Normalized Difference Vegetation Index"

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

    @property
    def collection_assets_to_use(self) -> dict[str, list[str]]:
        return {
            SENTINEL_2_L2A_COLLECTION_NAME: ["red", "nir"],
            LOCAL_COLLECTION_NAME: ["red", "nir"],
        }

    @staticmethod
    def calculate_index(
        raster_arr: xarray.DataArray,
        rescale_factor: float = 1e-5,
        rescale_offset: float = -0.1,
    ) -> xarray.DataArray:
        nir = rescale(raster_arr.sel(band="nir"), scale=rescale_factor, offset=rescale_offset)
        red = rescale(raster_arr.sel(band="red"), scale=rescale_factor, offset=rescale_offset)
        return ndvi(nir_agg=nir, red_agg=red).rio.write_crs(WGS84)


class NDWI(IndexCalculator):
    @property
    def name(self) -> str:
        return "ndwi"

    @property
    def full_name(self) -> str:
        return "Normalized Difference Water Index"

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

    @property
    def collection_assets_to_use(self) -> dict[str, list[str]]:
        return {
            SENTINEL_2_L2A_COLLECTION_NAME: ["green", "nir"],
            LOCAL_COLLECTION_NAME: ["green", "nir"],
        }

    @staticmethod
    def calculate_index(
        raster_arr: xarray.DataArray,
        rescale_factor: float = 1e-5,
        rescale_offset: float = -0.1,
    ) -> xarray.DataArray:
        nir = rescale(raster_arr.sel(band="nir"), scale=rescale_factor, offset=rescale_offset)
        green = rescale(raster_arr.sel(band="green"), scale=rescale_factor, offset=rescale_offset)
        return ndvi(nir_agg=green, red_agg=nir, name="ndwi").rio.write_crs(WGS84)


class SAVI(IndexCalculator):
    @property
    def name(self) -> str:
        return "savi"

    @property
    def full_name(self) -> str:
        return "Soil Adjusted Vegetation Index"

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

    @property
    def collection_assets_to_use(self) -> dict[str, list[str]]:
        return {
            SENTINEL_2_L2A_COLLECTION_NAME: ["red", "nir"],
            LOCAL_COLLECTION_NAME: ["red", "nir"],
        }

    @staticmethod
    def calculate_index(
        raster_arr: xarray.DataArray,
        rescale_factor: float = 1e-5,
        rescale_offset: float = -0.1,
    ) -> xarray.DataArray:
        nir = rescale(raster_arr.sel(band="nir"), scale=rescale_factor, offset=rescale_offset)
        red = rescale(raster_arr.sel(band="red"), scale=rescale_factor, offset=rescale_offset)
        return savi(nir_agg=nir, red_agg=red).rio.write_crs(WGS84)


class EVI(IndexCalculator):
    @property
    def name(self) -> str:
        return "evi"

    @property
    def full_name(self) -> str:
        return "Enhanced Vegetation Index"

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

    @property
    def collection_assets_to_use(self) -> dict[str, list[str]]:
        return {
            SENTINEL_2_L2A_COLLECTION_NAME: ["blue", "red", "nir"],
            LOCAL_COLLECTION_NAME: ["blue", "red", "nir"],
        }

    @staticmethod
    def calculate_index(
        raster_arr: xarray.DataArray,
        rescale_factor: float = 1e-5,
        rescale_offset: float = -0.1,
    ) -> xarray.DataArray:
        nir = rescale(raster_arr.sel(band="nir"), scale=rescale_factor, offset=rescale_offset)
        red = rescale(raster_arr.sel(band="red"), scale=rescale_factor, offset=rescale_offset)
        blue = rescale(raster_arr.sel(band="blue"), scale=rescale_factor, offset=rescale_offset)
        return evi(nir_agg=nir, red_agg=red, blue_agg=blue).rio.write_crs(WGS84)


class CyaCells(IndexCalculator):
    @property
    def name(self) -> str:
        return "cya_cells"

    @property
    def full_name(self) -> str:
        return "Cyanobacteria Density (cells / mL)"

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

    @property
    def collection_assets_to_use(self) -> dict[str, list[str]]:
        return {
            SENTINEL_2_L2A_COLLECTION_NAME: ["blue", "green", "red", "scl"],
            LOCAL_COLLECTION_NAME: ["blue", "green", "red", "scl"],
        }

    @staticmethod
    def calculate_index(
        raster_arr: xarray.DataArray,
        rescale_factor: float = 1e-5,
        rescale_offset: float = -0.1,
    ) -> xarray.DataArray:
        water_mask = sentinel_water_mask(raster_arr.sel(band="scl"))
        return cya_cells_ml(
            blue_agg=rescale(raster_arr.sel(band="blue"), scale=rescale_factor, offset=rescale_offset),
            green_agg=rescale(raster_arr.sel(band="green"), scale=rescale_factor, offset=rescale_offset),
            red_agg=rescale(raster_arr.sel(band="red"), scale=rescale_factor, offset=rescale_offset),
            water_mask=water_mask,
            crs=raster_arr.rio.crs,
        )


class CyaMg(IndexCalculator):
    @property
    def name(self) -> str:
        return "cya_mg"

    @property
    def full_name(self) -> str:
        return "Cyanobacteria Density (mg / m3)"

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

    @property
    def collection_assets_to_use(self) -> dict[str, list[str]]:
        return {
            SENTINEL_2_L2A_COLLECTION_NAME: ["red", "rededge1", "scl"],
            LOCAL_COLLECTION_NAME: ["red", "rededge1", "scl"],
        }

    @staticmethod
    def calculate_index(
        raster_arr: xarray.DataArray,
        rescale_factor: float = 1e-5,
        rescale_offset: float = -0.1,
    ) -> xarray.DataArray:
        water_mask = sentinel_water_mask(raster_arr.sel(band="scl"))
        return cya_mg_m3(
            red_agg=rescale(raster_arr.sel(band="red"), scale=rescale_factor, offset=rescale_offset),
            red_edge_agg=rescale(raster_arr.sel(band="rededge1"), scale=rescale_factor, offset=rescale_offset),
            water_mask=water_mask,
            crs=raster_arr.rio.crs,
        )


class ChlACoastal(IndexCalculator):
    @property
    def name(self) -> str:
        return "chl_a_coastal"

    @property
    def full_name(self) -> str:
        return "Chlorophyll A (for coastal regions)"

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

    @property
    def collection_assets_to_use(self) -> dict[str, list[str]]:
        return {
            SENTINEL_2_L2A_COLLECTION_NAME: ["red", "rededge1", "scl"],
            LOCAL_COLLECTION_NAME: ["red", "rededge1", "scl"],
        }

    @staticmethod
    def calculate_index(
        raster_arr: xarray.DataArray,
        rescale_factor: float = 1e-5,
        rescale_offset: float = -0.1,
    ) -> xarray.DataArray:
        water_mask = sentinel_water_mask(raster_arr.sel(band="scl"))
        return chl_a_coastal(
            red_agg=rescale(raster_arr.sel(band="red"), scale=rescale_factor, offset=rescale_offset),
            red_edge_agg=rescale(raster_arr.sel(band="rededge1"), scale=rescale_factor, offset=rescale_offset),
            water_mask=water_mask,
            crs=raster_arr.rio.crs,
        )


class ChlALow(IndexCalculator):
    @property
    def name(self) -> str:
        return "chl_a_low"

    @property
    def full_name(self) -> str:
        return "Chlorophyll A (for low values)"

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

    @property
    def collection_assets_to_use(self) -> dict[str, list[str]]:
        return {
            SENTINEL_2_L2A_COLLECTION_NAME: ["blue", "green", "scl"],
            LOCAL_COLLECTION_NAME: ["blue", "green", "scl"],
        }

    @staticmethod
    def calculate_index(
        raster_arr: xarray.DataArray,
        rescale_factor: float = 1e-5,
        rescale_offset: float = -0.1,
    ) -> xarray.DataArray:
        water_mask = sentinel_water_mask(raster_arr.sel(band="scl"))
        return chl_a_low(
            blue_agg=rescale(raster_arr.sel(band="blue"), scale=rescale_factor, offset=rescale_offset),
            green_agg=rescale(raster_arr.sel(band="green"), scale=rescale_factor, offset=rescale_offset),
            water_mask=water_mask,
            crs=raster_arr.rio.crs,
        )


class ChlAHigh(IndexCalculator):
    @property
    def name(self) -> str:
        return "chl_a_high"

    @property
    def full_name(self) -> str:
        return "Chlorophyll A (for high values)"

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

    @property
    def collection_assets_to_use(self) -> dict[str, list[str]]:
        return {
            SENTINEL_2_L2A_COLLECTION_NAME: ["red", "rededge1", "scl"],
            LOCAL_COLLECTION_NAME: ["red", "rededge1", "scl"],
        }

    @staticmethod
    def calculate_index(
        raster_arr: xarray.DataArray,
        rescale_factor: float = 1e-5,
        rescale_offset: float = -0.1,
    ) -> xarray.DataArray:
        water_mask = sentinel_water_mask(raster_arr.sel(band="scl"))
        return chl_a_high(
            red_agg=rescale(raster_arr.sel(band="red"), scale=rescale_factor, offset=rescale_offset),
            red_edge_agg=rescale(raster_arr.sel(band="rededge1"), scale=rescale_factor, offset=rescale_offset),
            water_mask=water_mask,
            crs=raster_arr.rio.crs,
        )


class Turbidity(IndexCalculator):
    @property
    def name(self) -> str:
        return "turb"

    @property
    def full_name(self) -> str:
        return "Turbidity"

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

    @property
    def collection_assets_to_use(self) -> dict[str, list[str]]:
        return {
            SENTINEL_2_L2A_COLLECTION_NAME: ["blue", "rededge1", "scl"],
            LOCAL_COLLECTION_NAME: ["blue", "rededge1", "scl"],
        }

    @staticmethod
    def calculate_index(
        raster_arr: xarray.DataArray,
        rescale_factor: float = 1e-5,
        rescale_offset: float = -0.1,
    ) -> xarray.DataArray:
        water_mask = sentinel_water_mask(raster_arr.sel(band="scl"))
        return turb(
            blue_agg=rescale(raster_arr.sel(band="blue"), scale=rescale_factor, offset=rescale_offset),
            red_edge_agg=rescale(raster_arr.sel(band="rededge1"), scale=rescale_factor, offset=rescale_offset),
            water_mask=water_mask,
            crs=raster_arr.rio.crs,
        )


class DOC(IndexCalculator):
    @property
    def name(self) -> str:
        return "doc"

    @property
    def full_name(self) -> str:
        return "Dissolved Organic Carbon"

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

    @property
    def collection_assets_to_use(self) -> dict[str, list[str]]:
        return {
            SENTINEL_2_L2A_COLLECTION_NAME: ["green", "red", "scl"],
            LOCAL_COLLECTION_NAME: ["green", "red", "scl"],
        }

    @staticmethod
    def calculate_index(
        raster_arr: xarray.DataArray,
        rescale_factor: float = 1e-5,
        rescale_offset: float = -0.1,
    ) -> xarray.DataArray:
        water_mask = sentinel_water_mask(raster_arr.sel(band="scl"))
        return doc(
            green_agg=rescale(raster_arr.sel(band="green"), scale=rescale_factor, offset=rescale_offset),
            red_agg=rescale(raster_arr.sel(band="red"), scale=rescale_factor, offset=rescale_offset),
            water_mask=water_mask,
            crs=raster_arr.rio.crs,
        )


class CDOM(IndexCalculator):
    @property
    def name(self) -> str:
        return "cdom"

    @property
    def full_name(self) -> str:
        return "Colored Dissolved Organic Matter"

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

    @property
    def collection_assets_to_use(self) -> dict[str, list[str]]:
        return {
            SENTINEL_2_L2A_COLLECTION_NAME: ["blue", "red", "scl"],
            LOCAL_COLLECTION_NAME: ["blue", "red", "scl"],
        }

    @staticmethod
    def calculate_index(
        raster_arr: xarray.DataArray,
        rescale_factor: float = 1e-5,
        rescale_offset: float = -0.1,
    ) -> xarray.DataArray:
        water_mask = sentinel_water_mask(raster_arr.sel(band="scl"))
        return cdom(
            blue_agg=rescale(raster_arr.sel(band="blue"), scale=rescale_factor, offset=rescale_offset),
            red_agg=rescale(raster_arr.sel(band="red"), scale=rescale_factor, offset=rescale_offset),
            water_mask=water_mask,
            crs=raster_arr.rio.crs,
        )


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
