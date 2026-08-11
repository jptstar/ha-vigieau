# SPDX-FileCopyrightText: 2026 Jean-Philippe TESTART (jptstar)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Constants for VigiEau France."""

DOMAIN = "vigieau_france"
NAME = "VigiEau France"
VERSION = "0.3.1"

VIGIEAU_API_BASE = "https://api.vigieau.gouv.fr/api"
GEOCODING_API_BASE = "https://data.geopf.fr/geocodage"
COMMUNES_API_BASE = "https://geo.api.gouv.fr"
VIGIEAU_WEBSITE = "https://vigieau.gouv.fr"

CONF_ADDRESS = "address"
CONF_LOCATION_MODE = "location_mode"
CONF_MAP_LOCATION = "map_location"
CONF_POSTAL_CODE = "postal_code"
CONF_LABEL = "label"
CONF_CITYCODE = "citycode"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_LOCATION_TYPE = "location_type"
CONF_PROFILE = "profile"
CONF_WATER_TYPE = "water_type"
CONF_ZONE_ID = "zone_id"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_PROFILE = "particulier"
DEFAULT_WATER_TYPE = "AEP"
DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 15
MAX_SCAN_INTERVAL = 1440

LOCATION_MODE_ADDRESS = "address"
LOCATION_MODE_HOME = "home"
LOCATION_MODE_POSTAL_CODE = "postal_code"
LOCATION_MODE_MAP = "map"
LOCATION_MODES = (
    LOCATION_MODE_ADDRESS,
    LOCATION_MODE_HOME,
    LOCATION_MODE_POSTAL_CODE,
    LOCATION_MODE_MAP,
)

PROFILES = {
    "particulier": "particulier",
    "entreprise": "professionnel",
    "collectivite": "collectivité",
    "exploitation": "exploitation agricole",
}

WATER_TYPES = {
    "AEP": "Eau potable",
    "SUP": "Eau superficielle",
    "SOU": "Eau souterraine",
}

SEVERITY_RANK = {
    "vigilance": 1,
    "alerte": 2,
    "alerte_renforcee": 3,
    "crise": 4,
}

SEVERITY_LABEL = {
    "vigilance": "vigilance",
    "alerte": "alerte",
    "alerte_renforcee": "alerte renforcée",
    "crise": "crise",
}

VIGILANCE_WITH_RESTRICTIONS_DEPARTMENTS = {"59", "62"}
ATTRIBUTION = "Données fournies par VigiEau (vigieau.gouv.fr)"
