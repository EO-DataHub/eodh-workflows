from __future__ import annotations

from typing import TYPE_CHECKING

from src.consts.crs import WGS84
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from pathlib import Path

    import xarray

_logger = get_logger(__name__)


def save_cog(arr: xarray.DataArray, item_id: str, output_dir: Path, epsg: int = WGS84) -> Path:
    _logger.info("Saving '%s' COG to %s", item_id, output_dir.as_posix())
    output_dir.mkdir(parents=True, exist_ok=True)

    if arr.rio.crs is None:
        _logger.warning("CRS on `rio` accessor for item '%s' was not set. Will assume %s", item_id, epsg)
        arr = arr.rio.write_crs(epsg=epsg)

    if arr.rio.crs.to_epsg() != epsg:
        arr = arr.rio.reproject(f"EPSG:{epsg}")

    arr = arr.rio.write_crs(f"EPSG:{epsg}")
    arr.rio.to_raster(output_dir / f"{item_id}.tif", driver="COG", windowed=True)

    return output_dir / f"{item_id}.tif"
