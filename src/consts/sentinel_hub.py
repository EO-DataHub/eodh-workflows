from __future__ import annotations

SH_AUTHENTICATON_TOKEN_ENDPOINT = "https://services.sentinel-hub.com/auth/realms/main/protocol/openid-connect/token"

SH_PROCESS_API = "https://creodias.sentinel-hub.com/api/v1/process"

SH_EVALSCRIPT_CORINELC = """
    function setup() {
        return {
            input: ["CLC"],
            output: {
                bands: 1,
                sampleType: "UINT16"
            }
        };
    }

    function evaluatePixel(sample) {
        return [sample.CLC];
    }
"""

SH_CLASSES_DICT_CORINELC = [
    {"value": 1, "description": "Continuous urban fabric", "color-hint": "e6004d"},
    {"value": 2, "description": "Discontinuous urban fabric", "color-hint": "ff0000"},
    {"value": 3, "description": "Industrial or commercial units", "color-hint": "cc4df2"},
    {"value": 4, "description": "Road and rail networks and associated land", "color-hint": "cc0000"},
    {"value": 5, "description": "Port areas", "color-hint": "e6cccc"},
    {"value": 6, "description": "Airports", "color-hint": "e6cce6"},
    {"value": 7, "description": "Mineral extraction sites", "color-hint": "600cc"},
    {"value": 8, "description": "Dump sites", "color-hint": "a64d00"},
    {"value": 9, "description": "Construction sites", "color-hint": "ff4dff"},
    {"value": 10, "description": "Green urban areas", "color-hint": "ffa6ff"},
    {"value": 11, "description": "Sport and leisure facilities", "color-hint": "ffe6ff"},
    {"value": 12, "description": "Non-irrigated arable land", "color-hint": "ffffa8"},
    {"value": 13, "description": "Permanently irrigated land", "color-hint": "ffff00"},
    {"value": 14, "description": "Rice fields", "color-hint": "6e600"},
    {"value": 15, "description": "Vineyards", "color-hint": "e68000"},
    {"value": 16, "description": "Fruit trees and berry plantations", "color-hint": "f2a64d"},
    {"value": 17, "description": "Olive groves", "color-hint": "e6a600"},
    {"value": 18, "description": "Pastures", "color-hint": "e6e64d"},
    {"value": 19, "description": "Annual crops associated with permanent crops", "color-hint": "ffe6a6"},
    {"value": 20, "description": "Complex cultivation patterns", "color-hint": "ffe64d"},
    {
        "value": 21,
        "description": "Land principally occupied by agriculture with significant areas of natural vegetation",
        "color-hint": "e6cc4d",
    },
    {"value": 22, "description": "Agro-forestry areas", "color-hint": "f2cca6"},
    {"value": 23, "description": "Broad-leaved forest", "color-hint": "80ff00"},
    {"value": 24, "description": "Coniferous forest", "color-hint": "00a600"},
    {"value": 25, "description": "Mixed forest", "color-hint": "4dff00"},
    {"value": 26, "description": "Natural grasslands", "color-hint": "ccf24d"},
    {"value": 27, "description": "Moors and heathland", "color-hint": "a6ff80"},
    {"value": 28, "description": "Sclerophyllous vegetation", "color-hint": "a6e64d"},
    {"value": 29, "description": "Transitional woodland-shrub", "color-hint": "a6f200"},
    {"value": 30, "description": "Beaches - dunes - sands", "color-hint": "e6e6e6"},
    {"value": 31, "description": "Bare rocks", "color-hint": "cccccc"},
    {"value": 32, "description": "Sparsely vegetated areas", "color-hint": "ccffcc"},
    {"value": 33, "description": "Burnt areas", "color-hint": "000000"},
    {"value": 34, "description": "Glaciers and perpetual snow", "color-hint": "a6e6cc"},
    {"value": 35, "description": "Inland marshes", "color-hint": "a6a6ff"},
    {"value": 36, "description": "Peat bogs", "color-hint": "4d4dff"},
    {"value": 37, "description": "Salt marshes", "color-hint": "ccccff"},
    {"value": 38, "description": "Salines", "color-hint": "e6e6ff"},
    {"value": 39, "description": "Intertidal flats", "color-hint": "a6a6e6"},
    {"value": 40, "description": "Water courses", "color-hint": "00ccf2"},
    {"value": 41, "description": "Water bodies", "color-hint": "80f2e6"},
    {"value": 42, "description": "Coastal lagoons", "color-hint": "00ffa6"},
    {"value": 43, "description": "Estuaries", "color-hint": "a6ffe6"},
    {"value": 44, "description": "Sea and ocean", "color-hint": "e6f2ff"},
    {"value": 48, "description": "NODATA", "color-hint": "ffffff"},
]
