from __future__ import annotations

# CEDA
CEDA_CATALOG_API_ENDPOINT = "https://api.stac.ceda.ac.uk/"
CEDA_ESACCI_LC_COLLECTION_NAME = "land_cover"
CEDA_ESACCI_LC_LOCAL_NAME = "esacci-globallc"

# Sentinel Hub
SH_CATALOG_API_ENDPOINT = "https://creodias.sentinel-hub.com/api/v1/catalog/1.0.0/"
SH_CLMS_CORINELC_COLLECTION_NAME = "byoc-cbdba844-f86d-41dc-95ad-b3f7f12535e9"
SH_CLMS_CORINELC_LOCAL_NAME = "clms-corinelc"
SH_CLMS_WATER_BODIES_COLLECTION_NAME = "byoc-62bf6f6a-c584-48a8-a739-0bc60efee54a"
SH_CLMS_WATER_BODIES_LOCAL_NAME = "clms-water-bodies"

# Planetary Computer
PC_CATALOG_API_ENDPOINT = "https://planetarycomputer.microsoft.com/api/stac/v1"

# EODH STAC API
EODH_CATALOG_API_ENDPOINT = "https://test.eodatahub.org.uk/api/catalogue/stac"

SENTINEL_2_L2A_COLLECTION_NAME = "sentinel-2-l2a"

STAC_COLLECTIONS = {
    SENTINEL_2_L2A_COLLECTION_NAME,
}

NDVI = "ndvi"
NDWI = "ndwi"
EVI = "evi"
SAVI = "savi"

INDEX_TO_ASSETS_LOOKUP: dict[str, dict[str, list[str]]] = {
    SENTINEL_2_L2A_COLLECTION_NAME: {
        NDVI: ["red", "nir"],
        NDWI: ["green", "nir"],
        EVI: ["blue", "red", "nir"],
        SAVI: ["red", "nir"],
    },
}
