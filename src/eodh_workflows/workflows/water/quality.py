from __future__ import annotations

import json
from pathlib import Path

import click

from eodh_workflows.consts.directories import LOCAL_DATA_DIR
from eodh_workflows.utils.logging import get_logger
from eodh_workflows.utils.raster import get_raster_bounds, save_cog
from eodh_workflows.utils.stac import (
    generate_stac,
    prepare_stac_asset,
    prepare_stac_item,
    read_local_stac,
)
from eodh_workflows.workflows.ds.utils import prepare_data_array
from eodh_workflows.workflows.spectral.indices import (
    CDOM,
    DOC,
    NDWI,
    CyaCells,
)
from eodh_workflows.workflows.spectral.utils import resolve_rescale_params

_logger = get_logger(__name__)


@click.command(help="Calculate water quality indices")
@click.option(
    "--data_dir",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    help="Path to the input STAC catalog directory",
)
@click.option(
    "--output_dir",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    help="Path to the output directory - will create new dir in CWD if not provided",
)
def water_quality(data_dir: Path, output_dir: Path | None = None) -> None:
    _logger.info(
        "Running with:\n%s",
        json.dumps(
            {
                "data_dir": data_dir.as_posix(),
                "output_dir": output_dir.as_posix() if output_dir is not None else None,
            },
            indent=4,
        ),
    )
    data_dir = data_dir.absolute()
    output_dir = output_dir or LOCAL_DATA_DIR / "water-quality"
    output_dir.mkdir(exist_ok=True, parents=True)

    output_items = []
    local_stac = read_local_stac(data_dir)
    local_stac.make_all_asset_hrefs_absolute()

    for item in local_stac.get_items(recursive=True):
        raster_arr = prepare_data_array(
            item=item,
            assets=["blue", "green", "red", "rededge1", "nir", "scl"]
            if "scl" in item.assets
            else ["blue", "green", "red", "rededge1", "nir", "swir16"],
        )
        first_asset = next(iter(item.assets.values()))
        asset_dir = Path(first_asset.href).parent
        asset_out_dir = output_dir / asset_dir.relative_to(data_dir)
        scale, offset = resolve_rescale_params(collection_name=item.collection_id, item_datetime=item.datetime)

        out_item = prepare_stac_item(
            id_item=item.id,
            geometry=get_raster_bounds(raster_arr),
            epsg=raster_arr.rio.crs.to_epsg(),
            transform=list(raster_arr.rio.transform()),
            datetime=item.datetime,
        )

        for index_calculator in [
            CDOM(),
            DOC(),
            CyaCells(),
            NDWI(),
        ]:
            _logger.info("Calculating %s index for item %s", index_calculator.full_name, item.id)

            index_raster = index_calculator.calculate_index(
                raster_arr=raster_arr,
                rescale_factor=scale,
                rescale_offset=offset,
            )
            raster_path = save_cog(
                arr=index_raster,
                asset_id=index_calculator.name.lower(),
                output_dir=asset_out_dir,
            )

            data_asset = prepare_stac_asset(
                title=index_calculator.full_name,
                file_path=raster_path,
                asset_extra_fields=index_calculator.asset_extra_fields(index_raster),
            )
            out_item.add_asset(index_calculator.name, data_asset)

        output_items.append(out_item)

    generate_stac(
        items=output_items,
        output_dir=output_dir,
        title="EOPro Water Quality calculation",
        description="Water Quality calculation",
    )
