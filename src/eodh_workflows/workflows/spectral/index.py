from __future__ import annotations

import json
from pathlib import Path

import click
from tqdm import tqdm

from eodh_workflows.consts.directories import LOCAL_DATA_DIR
from eodh_workflows.utils.logging import get_logger
from eodh_workflows.utils.raster import save_cog
from eodh_workflows.utils.stac import generate_stac, prepare_stac_asset, prepare_stac_item, read_local_stac
from eodh_workflows.workflows.spectral.indices import SPECTRAL_INDICES

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

    output_dir = output_dir or LOCAL_DATA_DIR / "spectral-index"
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
        assets = {
            index_calculator.name: prepare_stac_asset(
                file_path=fp.resolve().absolute(),
                title=index_calculator.full_name,
                asset_extra_fields=index_calculator.asset_extra_fields(index_raster),
            ),
        }
        items.append(
            prepare_stac_item(
                id_item=item.id,
                geometry=item.geometry,
                epsg=index_raster.rio.crs.to_epsg(),
                transform=list(index_raster.rio.transform()),
                datetime=item.datetime,
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
