from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Any

import numpy as np
from xrspatial.multispectral import evi, ndvi, savi

from src.utils.logging import get_logger
from src.workflows.ds.utils import prepare_data_array
from src.workflows.spectral.functional import (
    cdom,
    chl_a_coastal,
    chl_a_high,
    chl_a_low,
    cya_cells_ml,
    cya_mg_m3,
    doc,
    ndmi,
    ndwi,
    simple_ratio,
    turb,
)
from src.workflows.spectral.utils import raster_stats, rescale, resolve_rescale_params

if TYPE_CHECKING:
    import pystac
    import xarray

_logger = get_logger(__name__)
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
        return ndwi(nir_agg=nir, green_agg=green, crs=raster_arr.rio.crs)


class NDMI(IndexCalculator):
    @property
    def name(self) -> str:
        return "ndmi"

    @property
    def full_name(self) -> str:
        return "Normalized Difference Moisture Index (NDWI)"

    @property
    def typical_range(self) -> tuple[float, float, int]:
        return -1.0, 1.0, 20

    @property
    def units(self) -> str:
        return "NDMI"

    @property
    def mpl_colormap(self) -> tuple[str, bool]:
        return "RdBu", False

    @property
    def js_colormap(self) -> tuple[str, bool]:
        return "RdBu", False

    @staticmethod
    def collection_assets_to_use(item: pystac.Item) -> list[str]:  # noqa: ARG004
        return ["green", "swir16"]

    @staticmethod
    def calculate_index(
        raster_arr: xarray.DataArray,
        rescale_factor: float = 1e-4,
        rescale_offset: float = -0.1,
    ) -> xarray.DataArray:
        swir = rescale(raster_arr.sel(band="swir16"), scale=rescale_factor, offset=rescale_offset)
        green = rescale(raster_arr.sel(band="green"), scale=rescale_factor, offset=rescale_offset)
        return ndmi(swir_agg=swir, green_agg=green, crs=raster_arr.rio.crs)


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
        return ["blue", "green", "red", "scl"] if "scl" in item.assets else ["blue", "green", "red", "nir", "swir16"]

    @staticmethod
    def calculate_index(
        raster_arr: xarray.DataArray,
        rescale_factor: float = 1e-4,
        rescale_offset: float = -0.1,
    ) -> xarray.DataArray:
        idx = cya_cells_ml(
            blue_agg=rescale(raster_arr.sel(band="blue"), scale=rescale_factor, offset=rescale_offset),
            green_agg=rescale(raster_arr.sel(band="green"), scale=rescale_factor, offset=rescale_offset),
            red_agg=rescale(raster_arr.sel(band="red"), scale=rescale_factor, offset=rescale_offset),
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
        idx = cya_mg_m3(
            red_agg=rescale(raster_arr.sel(band="red"), scale=rescale_factor, offset=rescale_offset),
            red_edge_agg=rescale(raster_arr.sel(band="rededge1"), scale=rescale_factor, offset=rescale_offset),
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
        idx = chl_a_coastal(
            red_agg=rescale(raster_arr.sel(band="red"), scale=rescale_factor, offset=rescale_offset),
            red_edge_agg=rescale(raster_arr.sel(band="rededge1"), scale=rescale_factor, offset=rescale_offset),
            crs=raster_arr.rio.crs,
        )
        return idx.where(np.isfinite(idx), np.nan)


class BlueSwirRatio(IndexCalculator):
    @property
    def name(self) -> str:
        return "blue_swir_ratio"

    @property
    def full_name(self) -> str:
        return "Simple ratio (Blue/SWIR)"

    @property
    def typical_range(self) -> tuple[float, float, int]:
        return 0, 2, 20

    @property
    def units(self) -> str:
        return "Ratio"

    @property
    def mpl_colormap(self) -> tuple[str, bool]:
        return "jet", False

    @property
    def js_colormap(self) -> tuple[str, bool]:
        return "jet", False

    @staticmethod
    def collection_assets_to_use(item: pystac.Item) -> list[str]:
        return ["blue", "swir16", "scl"] if "scl" in item.assets else ["blue", "swir16"]

    @staticmethod
    def calculate_index(
        raster_arr: xarray.DataArray,
        rescale_factor: float = 1e-4,
        rescale_offset: float = -0.1,
    ) -> xarray.DataArray:
        idx = simple_ratio(
            band1=rescale(raster_arr.sel(band="blue"), scale=rescale_factor, offset=rescale_offset),
            band2=rescale(raster_arr.sel(band="swir16"), scale=rescale_factor, offset=rescale_offset),
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
        idx = chl_a_low(
            blue_agg=rescale(raster_arr.sel(band="blue"), scale=rescale_factor, offset=rescale_offset),
            green_agg=rescale(raster_arr.sel(band="green"), scale=rescale_factor, offset=rescale_offset),
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
        idx = chl_a_high(
            red_agg=rescale(raster_arr.sel(band="red"), scale=rescale_factor, offset=rescale_offset),
            red_edge_agg=rescale(raster_arr.sel(band="rededge1"), scale=rescale_factor, offset=rescale_offset),
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
        idx = turb(
            blue_agg=rescale(raster_arr.sel(band="blue"), scale=rescale_factor, offset=rescale_offset),
            red_edge_agg=rescale(raster_arr.sel(band="rededge1"), scale=rescale_factor, offset=rescale_offset),
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
        idx = doc(
            green_agg=rescale(raster_arr.sel(band="green"), scale=rescale_factor, offset=rescale_offset),
            red_agg=rescale(raster_arr.sel(band="red"), scale=rescale_factor, offset=rescale_offset),
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
        idx = cdom(
            blue_agg=rescale(raster_arr.sel(band="blue"), scale=rescale_factor, offset=rescale_offset),
            red_agg=rescale(raster_arr.sel(band="red"), scale=rescale_factor, offset=rescale_offset),
            crs=raster_arr.rio.crs,
        )
        return idx.where(np.isfinite(idx), np.nan)


_SPECTRAL_INDEX_CLS: set[type[IndexCalculator]] = {
    NDVI,
    NDWI,
    NDMI,
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
    BlueSwirRatio,
}
SPECTRAL_INDICES = {cls().name: cls() for cls in _SPECTRAL_INDEX_CLS}
