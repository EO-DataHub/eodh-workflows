from __future__ import annotations

from src import consts


def get_classes_orig_dict(source, item) -> list[dict[str, int | str]]:
    if source.name == consts.stac.CEDA_ESACCI_LC_LOCAL_NAME:
        return item.assets["GeoTIFF"].extra_fields["classification:classes"]
    if source.name == consts.stac.SH_CLMS_CORINELC_LOCAL_NAME:
        return consts.sentinel_hub.SH_CLASSES_DICT_CORINELC


def get_classes(classes_dict: list[dict[str, int | str]]) -> set[int]:
    # Get unique classes
    # For the first item only, the rest is the same
    return {int(raster_value["value"]) for raster_value in classes_dict}
