from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from src.local_stac.generate import LOCAL_STAC_OUTPUT_DIR

if TYPE_CHECKING:
    import xarray


def save_cog(index_raster: xarray.DataArray, item_id: str, output_dir: Path | None = None, epsg: int = 4326) -> Path:
    if output_dir is None:
        output_dir = LOCAL_STAC_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    if index_raster.rio.crs.to_epsg() != epsg:
        index_raster = index_raster.rio.reproject(f"EPSG:{epsg}")

    index_raster = index_raster.rio.write_crs(f"EPSG:{epsg}")
    index_raster.rio.to_raster(output_dir / f"{item_id}.tif", driver="COG", windowed=True)

    return Path(output_dir / f"{item_id}.tif")
