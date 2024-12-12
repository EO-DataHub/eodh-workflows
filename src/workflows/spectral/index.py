from __future__ import annotations

import json
from pathlib import Path

import click
import numpy as np
from tqdm import tqdm

from src.consts.directories import LOCAL_STAC_OUTPUT_DIR
from src.utils.logging import get_logger
from src.utils.raster import save_cog
from src.utils.stac import generate_stac, prepare_stac_asset, prepare_stac_item, read_local_stac
from src.workflows.raster.indices import SPECTRAL_INDICES

_logger = get_logger(__name__)


@click.command(help="Clip (crop) rasters in STAC to specified AOI.")
@click.option(
    "--data_dir",
    required=True,
    type=click.Path(path_type=Path, resolve_path=True),  # type: ignore[type-var]
    help="Path to the local STAC folder",
)
@click.option(
    "--index",
    default="NDVI",
    type=click.Choice(SPECTRAL_INDICES, case_sensitive=False),
    show_default=True,
    help="The spectral index to calculate",
)
@click.option(
    "--output_dir",
    required=False,
    type=click.Path(path_type=Path, resolve_path=True),  # type: ignore[type-var]
    help="Path to the output directory - will create new dir in CWD if not provided",
)
def spectral_index(data_dir: Path, index: str, output_dir: Path | None = None) -> None:
    _logger.info(
        "Running with:\n%s",
        json.dumps(
            {
                "data_dir": data_dir.as_posix(),
                "index": index,
                "output_dir": output_dir.as_posix() if output_dir is not None else None,
            },
            indent=4,
        ),
    )

    output_dir = output_dir or LOCAL_STAC_OUTPUT_DIR
    output_dir.mkdir(exist_ok=True, parents=True)

    local_stac = read_local_stac(data_dir)

    index_calculator = SPECTRAL_INDICES[index]

    items = []
    for item in tqdm(list(local_stac.get_items(recursive=True)), desc="Processing STAC items"):
        first_asset = next(iter(item.assets.values()))
        asset_dir = Path(first_asset.href).parent
        index_raster = index_calculator.compute(item=item)
        fp = save_cog(
            arr=index_raster,
            asset_id=index,
            output_dir=output_dir / asset_dir.relative_to(data_dir),
        )
        vmin, vmax, intervals = index_calculator.typical_range
        js_cmap, cmap_reversed = index_calculator.js_colormap
        assets = {
            "ndvi": prepare_stac_asset(
                file_path=fp.resolve().absolute(),
                title=index_calculator.full_name,
                asset_extra_fields={
                    "colormap": {
                        "name": js_cmap,
                        "reversed": cmap_reversed,
                        "min": vmin,
                        "max": vmax,
                        "steps": intervals,
                        "units": index_calculator.units,
                        "mpl_equivalent_cmap": index_calculator.mpl_colormap[0],
                    },
                    "statistics": {
                        "minimum": index_raster.min().item(),
                        "maximum": index_raster.max().item(),
                        "mean": index_raster.mean().item(),
                        "median": index_raster.median().item(),
                        "stddev": index_raster.std().item(),
                        "valid_percent": (np.isnan(index_raster.data).sum() / np.prod(index_raster.shape)).item(),
                    },
                    "raster:bands": [
                        {
                            "nodata": np.nan,
                            "unit": index_calculator.units,
                        }
                    ],
                    "proj:shape": index_raster.shape,
                    "proj:transform": list(index_raster.rio.transform()),
                    "proj:epsg": index_raster.rio.crs.to_epsg(),
                },
            ),
        }
        items.append(
            prepare_stac_item(
                id_item=item.id,
                geometry=item.geometry,
                epsg=index_raster.rio.crs.to_epsg(),
                transform=list(index_raster.rio.transform()),
                datetime=item.datetime,
                additional_prop={},
                assets=assets,
            )
        )

    # Save local STAC
    generate_stac(
        items=items,
        output_dir=output_dir,
        title=f"EOPro {index.upper()} calculation",
        description=f"EOPro {index.upper()} calculation",
    )
