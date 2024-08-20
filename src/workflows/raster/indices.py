from __future__ import annotations

from typing import TYPE_CHECKING

from src import consts

if TYPE_CHECKING:
    import xarray


def calculate_index(index: str, raster_arr: xarray.DataArray) -> xarray.DataArray:
    func = index_calculation_func_lookup[index]
    return func(raster_arr)


def ndvi(raster_arr: xarray.DataArray) -> xarray.DataArray:
    # Assumes common names for bands
    nir = raster_arr.sel(band="nir")
    red = raster_arr.sel(band="red")
    return ((nir - red) / ((nir + red) + consts.compute.EPS)).compute()


def ndwi(raster_arr: xarray.DataArray) -> xarray.DataArray:
    # Assumes common names for bands
    nir = raster_arr.sel(band="nir")
    green = raster_arr.sel(band="green")
    return ((nir - green) / ((nir + green) + consts.compute.EPS)).compute()


def evi(raster_arr: xarray.DataArray) -> xarray.DataArray:
    # Assumes common names for bands
    nir = raster_arr.sel(band="nir")
    red = raster_arr.sel(band="red")
    blue = raster_arr.sel(band="blue")
    return (2.5 * ((nir - red) / ((nir + 6 * red - 7.5 * blue) + 1.0 + consts.compute.EPS))).compute()


def savi(raster_arr: xarray.DataArray) -> xarray.DataArray:
    # Assumes common names for bands
    nir = raster_arr.sel(band="nir")
    red = raster_arr.sel(band="red")
    return ((1 + 0.5) * (nir - red) / ((nir + red + 0.5) + consts.compute.EPS)).compute()


index_calculation_func_lookup = {"ndvi": ndvi, "ndwi": ndwi, "evi": evi, "savi": savi}
