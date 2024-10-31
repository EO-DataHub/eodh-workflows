from __future__ import annotations

from typing import TYPE_CHECKING

from xrspatial.multispectral import evi as _evi, ndvi as _ndvi, savi as _savi

from src.utils.logging import get_logger

if TYPE_CHECKING:
    import xarray

_logger = get_logger(__name__)


def ndvi(raster_arr: xarray.DataArray) -> xarray.DataArray:
    # Assumes common names for bands
    nir = raster_arr.sel(band="nir")
    red = raster_arr.sel(band="red")
    return _ndvi(nir_agg=nir, red_agg=red)


def ndwi(raster_arr: xarray.DataArray) -> xarray.DataArray:
    # Assumes common names for bands
    nir = raster_arr.sel(band="nir")
    green = raster_arr.sel(band="green")
    return _ndvi(nir_agg=green, red_agg=nir, name="ndwi")


def evi(raster_arr: xarray.DataArray) -> xarray.DataArray:
    # Assumes common names for bands
    nir = raster_arr.sel(band="nir")
    red = raster_arr.sel(band="red")
    blue = raster_arr.sel(band="blue")
    return _evi(nir_agg=nir, red_agg=red, blue_agg=blue)


def savi(raster_arr: xarray.DataArray) -> xarray.DataArray:
    # Assumes common names for bands
    nir = raster_arr.sel(band="nir")
    red = raster_arr.sel(band="red")
    return _savi(nir_agg=nir, red_agg=red)


index_calculation_func_lookup = {"ndvi": ndvi, "ndwi": ndwi, "evi": evi, "savi": savi}


def calculate_index(index: str, raster_arr: xarray.DataArray) -> xarray.DataArray:
    _logger.info("Calculating index: %s", index)
    func = index_calculation_func_lookup[index]
    return func(raster_arr)
