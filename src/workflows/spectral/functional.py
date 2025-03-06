from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import xarray

from src.consts.compute import EPS

if TYPE_CHECKING:
    from rasterio import CRS


def simple_ratio(
    band1: xarray.DataArray,
    band2: xarray.DataArray,
    crs: int | str | CRS,
    name: str = "ratio",
) -> xarray.DataArray:
    data = band1 / band2
    return xarray.DataArray(
        data,
        name=name,
        coords=band1.coords,
        dims=band1.dims,
        attrs=band1.attrs,
    ).rio.write_crs(crs)


def ndmi(
    green_agg: xarray.DataArray,
    swir_agg: xarray.DataArray,
    crs: int | str | CRS,
) -> xarray.DataArray:
    """Calculates Normalized Difference Moisture Index (NDMI).

    Args:
        green_agg: Green band (Sentinel-2 B03) data array with reflectance data.
        swir_agg: SWIR band (Sentinel-2 B10) data array with reflectance data.
        crs: CRS to write to the output array.

    Returns:
        NDMI index array.

    """
    ndmi_arr = (green_agg - swir_agg) / (swir_agg + green_agg + EPS)
    return xarray.DataArray(
        ndmi_arr,
        name="ndmi",
        coords=green_agg.coords,
        dims=green_agg.dims,
        attrs=green_agg.attrs,
    ).rio.write_crs(crs)


def cya_cells_ml(
    blue_agg: xarray.DataArray,
    green_agg: xarray.DataArray,
    red_agg: xarray.DataArray,
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
        crs: CRS to write to the output array.

    Returns:
        Data array with Cyanobacteria in 1e6 cells / mL.

    """
    data = 115_530.31 * ((green_agg * red_agg / (blue_agg + EPS)) ** 2.38)
    return xarray.DataArray(
        data,
        name="cya",
        coords=red_agg.coords,
        dims=red_agg.dims,
        attrs=red_agg.attrs,
    ).rio.write_crs(crs)


def cya_mg_m3(
    red_agg: xarray.DataArray,
    red_edge_agg: xarray.DataArray,
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
        crs: CRS to write to the output array.

    Returns:
        Data array with Cyanobacteria in mg / m3.

    """
    data = 21.554 * ((red_edge_agg / (red_agg + EPS)) ** 3.4791)
    return xarray.DataArray(
        data,
        name="cya",
        coords=red_agg.coords,
        dims=red_agg.dims,
        attrs=red_agg.attrs,
    ).rio.write_crs(crs)


def chl_a_high(
    red_agg: xarray.DataArray,
    red_edge_agg: xarray.DataArray,
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
        crs: CRS to write to the output array.

    Returns:
        Data array with Chl-a in mg / m3.

    """
    data = 19.866 * ((red_edge_agg / (red_agg + EPS)) ** 2.3051)
    return xarray.DataArray(
        data,
        name="chl-a-high",
        coords=red_edge_agg.coords,
        dims=red_edge_agg.dims,
        attrs=red_edge_agg.attrs,
    ).rio.write_crs(crs)


def chl_a_low(
    blue_agg: xarray.DataArray,
    green_agg: xarray.DataArray,
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
        crs: CRS to write to the output array.

    Returns:
        Data array with Chl-a in mg / m3.

    """
    data = np.exp(-2.4792 * (np.log10(np.maximum(green_agg, blue_agg) / (green_agg + EPS))) - 0.0389)
    return xarray.DataArray(
        data,
        name="chl-a-low",
        coords=blue_agg.coords,
        dims=blue_agg.dims,
        attrs=blue_agg.attrs,
    ).rio.write_crs(crs)


def chl_a_coastal(
    red_agg: xarray.DataArray,
    red_edge_agg: xarray.DataArray,
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
    return xarray.DataArray(
        data,
        name="chl-a-coastal",
        coords=red_agg.coords,
        dims=red_agg.dims,
        attrs=red_agg.attrs,
    ).rio.write_crs(crs)


def turb(
    blue_agg: xarray.DataArray,
    red_edge_agg: xarray.DataArray,
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
        crs: CRS to write to the output array.

    Returns:
        Data array with Turbidity in NTU.

    """
    data = 194.79 * (red_edge_agg * (red_edge_agg / (blue_agg + EPS))) + 0.9061
    return xarray.DataArray(
        data,
        name="turb",
        coords=red_edge_agg.coords,
        dims=red_edge_agg.dims,
        attrs=red_edge_agg.attrs,
    ).rio.write_crs(crs)


def cdom(
    blue_agg: xarray.DataArray,
    red_agg: xarray.DataArray,
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
        crs: CRS to write to the output array.

    Returns:
        CDOM in ug / L.
    """
    data = 2.4072 * (red_agg / (blue_agg + EPS)) + 0.0709
    return xarray.DataArray(
        data,
        name="cdom",
        coords=blue_agg.coords,
        dims=blue_agg.dims,
        attrs=blue_agg.attrs,
    ).rio.write_crs(crs)


def doc(
    green_agg: xarray.DataArray,
    red_agg: xarray.DataArray,
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
        crs: CRS to write to the output array.

    Returns:
        DOC in mg / L.
    """
    data = 432 * np.exp(-2.24 * (green_agg / (red_agg + EPS)) + EPS)
    return xarray.DataArray(
        data,
        name="doc",
        coords=red_agg.coords,
        dims=red_agg.dims,
        attrs=red_agg.attrs,
    ).rio.write_crs(crs)


def ndwi(
    green_agg: xarray.DataArray,
    nir_agg: xarray.DataArray,
    crs: int | str | CRS,
) -> xarray.DataArray:
    """Normalized Difference Water Index (NDWI).

    Args:
        green_agg: Green band (Sentinel-2 B03) data array with reflectance data.
        nir_agg: NIR band (Sentinel-2 B08) data array with reflectance data.
        crs: CRS to write to the output array.

    Returns:
        NDWI array.

    """
    data = (green_agg - nir_agg) / (nir_agg + green_agg + EPS)
    return xarray.DataArray(
        data,
        name="ndwi",
        coords=nir_agg.coords,
        dims=nir_agg.dims,
        attrs=nir_agg.attrs,
    ).rio.write_crs(crs)
