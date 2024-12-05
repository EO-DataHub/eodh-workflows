from __future__ import annotations

from typing import TYPE_CHECKING, cast

from src import consts

if TYPE_CHECKING:
    from pystac import Item

    from src.workflows.raster.download import DataSource


def get_classes_orig_dict(source: DataSource, item: Item) -> list[dict[str, int | str]]:
    if source.name == consts.stac.CEDA_ESACCI_LC_LOCAL_NAME:
        return cast(list[dict[str, int | str]], item.assets["GeoTIFF"].extra_fields["classification:classes"])
    if source.name == consts.stac.SH_CLMS_CORINELC_LOCAL_NAME:
        return cast(list[dict[str, int | str]], consts.sentinel_hub.SH_CLASSES_DICT_CORINELC)
    if source.name == consts.stac.SH_CLMS_WATER_BODIES_LOCAL_NAME:
        return cast(list[dict[str, int | str]], consts.sentinel_hub.SH_CLASSES_DICT_WATERBODIES)
    error_message = f"Unsupported data source: {source.name}"
    raise ValueError(error_message)


def get_classes(classes_dict: list[dict[str, int | str]]) -> set[int]:
    # Get unique classes
    # For the first item only, the rest is the same
    return {int(raster_value["value"]) for raster_value in classes_dict}
