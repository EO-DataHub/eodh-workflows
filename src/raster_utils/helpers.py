from __future__ import annotations

from typing import TYPE_CHECKING

import geopandas as gpd
import numpy as np
from rasterio.features import shapes
from shapely.geometry import MultiPolygon, Polygon, box, shape

if TYPE_CHECKING:
    import xarray as xr


def get_raster_bounds(xarr: xr.DataArray) -> Polygon:
    """Calculates bounds for the raster array."""
    bbox = xarr.rio.bounds()
    minx, miny, maxx, maxy = bbox

    return box(minx, miny, maxx, maxy)


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
    unified_polygon = polygons[0] if len(polygons) == 1 else MultiPolygon(polygons).union

    gdf = gpd.GeoDataFrame([{"geometry": unified_polygon, "name": "Convex Hull"}], crs=xarr.rio.crs)
    gdf.to_file(r"C:\Users\jas\eodh-workflows\data\test.geojson", driver="GeoJSON")

    return unified_polygon
