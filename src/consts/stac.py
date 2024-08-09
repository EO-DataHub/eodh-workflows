from __future__ import annotations

CATALOG_API_ENDPOINT = "https://planetarycomputer.microsoft.com/api/stac/v1"

SENTINEL_1_GRD_COLLECTION_NAME = "sentinel-1-grd"
SENTINEL_1_RTC_COLLECTION_NAME = "sentinel-1-rtc"
SENTINEL_2_L1C_COLLECTION_NAME = "sentinel-2-l1c"
SENTINEL_2_L2A_COLLECTION_NAME = "sentinel-2-l2a"

STAC_COLLECTIONS = {
    SENTINEL_1_GRD_COLLECTION_NAME,
    SENTINEL_1_RTC_COLLECTION_NAME,
    SENTINEL_2_L1C_COLLECTION_NAME,
    SENTINEL_2_L2A_COLLECTION_NAME,
}

NDVI = "ndvi"
NDWI = "ndwi"
EVI = "evi"
SAVI = "savi"

INDEX_TO_ASSETS_LOOKUP: dict[str, dict[str, list[str]]] = {
    SENTINEL_1_GRD_COLLECTION_NAME: {},
    SENTINEL_1_RTC_COLLECTION_NAME: {},
    SENTINEL_2_L1C_COLLECTION_NAME: {
        NDVI: ["B04", "B08"],
        NDWI: ["B03", "B08"],
        EVI: ["B02", "B03", "B08"],
        SAVI: ["B04", "B08"],
    },
    SENTINEL_2_L2A_COLLECTION_NAME: {
        NDVI: ["B04", "B08"],
        NDWI: ["B03", "B08"],
        EVI: ["B02", "B03", "B08"],
        SAVI: ["B04", "B08"],
    },
}
