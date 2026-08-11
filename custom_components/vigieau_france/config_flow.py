# SPDX-FileCopyrightText: 2026 Jean-Philippe TESTART (jptstar)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Config flow for VigiEau France."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    LocationSelector,
    LocationSelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from .api import (
    VigiEauApi,
    VigiEauConnectionError,
    VigiEauError,
    VigiEauNeedPreciseLocation,
    VigiEauNoActiveOrder,
)
from .const import (
    CONF_ADDRESS,
    CONF_CITYCODE,
    CONF_LABEL,
    CONF_LATITUDE,
    CONF_LOCATION_MODE,
    CONF_LOCATION_TYPE,
    CONF_LONGITUDE,
    CONF_MAP_LOCATION,
    CONF_POSTAL_CODE,
    CONF_PROFILE,
    CONF_SCAN_INTERVAL,
    CONF_WATER_TYPE,
    CONF_ZONE_ID,
    DEFAULT_PROFILE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_WATER_TYPE,
    DOMAIN,
    LOCATION_MODE_ADDRESS,
    LOCATION_MODE_HOME,
    LOCATION_MODE_MAP,
    LOCATION_MODE_POSTAL_CODE,
    LOCATION_MODES,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    PROFILES,
)
from .logic import format_zones, zones_for_water_type
from .models import AddressCandidate, Zone

PROFILE_CHOICES = {key: label.capitalize() for key, label in PROFILES.items()}
WATER_CHOICES = {
    "AEP": "du robinet",
    "SUP": "d'un cours d'eau, d'une rivière",
    "SOU": "des nappes (puits ou forage)",
}


class VigiEauFranceConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle VigiEau France setup."""

    VERSION = 1

    def __init__(self) -> None:
        self._candidates: list[AddressCandidate] = []
        self._pending_location: AddressCandidate | None = None
        self._pending_profile = DEFAULT_PROFILE
        self._pending_water_type = DEFAULT_WATER_TYPE
        self._pending_location_mode = LOCATION_MODE_ADDRESS
        self._pending_zones: tuple[Zone, ...] = ()

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Choose how the location will be provided."""
        errors: dict[str, str] = {}
        if user_input is not None:
            mode = str(user_input[CONF_LOCATION_MODE])
            self._pending_location_mode = mode
            if mode == LOCATION_MODE_ADDRESS:
                return await self.async_step_address()
            if mode == LOCATION_MODE_POSTAL_CODE:
                return await self.async_step_postal_code()
            if mode == LOCATION_MODE_MAP:
                return await self.async_step_map()

            api = VigiEauApi(async_get_clientsession(self.hass))
            try:
                location = await api.async_reverse_location(
                    float(self.hass.config.latitude),
                    float(self.hass.config.longitude),
                    location_type=LOCATION_MODE_HOME,
                )
            except (VigiEauConnectionError, VigiEauError):
                errors["base"] = "cannot_connect"
            else:
                if location is None:
                    errors["base"] = "location_not_found"
                else:
                    self._pending_location = location
                    return await self.async_step_preferences()

        return self.async_show_form(
            step_id="user",
            data_schema=self._location_mode_schema(),
            errors=errors,
        )

    def _location_mode_schema(self) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required(
                    CONF_LOCATION_MODE,
                    default=self._pending_location_mode,
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=list(LOCATION_MODES),
                        mode=SelectSelectorMode.LIST,
                        translation_key="location_mode",
                    )
                )
            }
        )

    def _address_schema(self) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required(CONF_ADDRESS): TextSelector(
                    TextSelectorConfig(autocomplete="street-address")
                )
            }
        )

    async def async_step_address(self, user_input: dict[str, Any] | None = None):
        """Search for a precise address."""
        errors: dict[str, str] = {}
        if user_input is not None:
            api = VigiEauApi(async_get_clientsession(self.hass))
            try:
                self._candidates = await api.async_search_addresses(
                    str(user_input[CONF_ADDRESS])
                )
            except (VigiEauConnectionError, VigiEauError):
                errors["base"] = "cannot_connect"
            else:
                if not self._candidates:
                    errors["base"] = "address_not_found"
                elif len(self._candidates) == 1:
                    self._pending_location = self._candidates[0]
                    return await self.async_step_preferences()
                else:
                    return await self.async_step_location()

        return self.async_show_form(
            step_id="address",
            data_schema=self._address_schema(),
            errors=errors,
        )

    async def async_step_postal_code(self, user_input: dict[str, Any] | None = None):
        """Resolve a French postal code to one or more communes."""
        errors: dict[str, str] = {}
        if user_input is not None:
            postal_code = str(user_input[CONF_POSTAL_CODE]).strip()
            if len(postal_code) != 5 or not postal_code.isdigit():
                errors[CONF_POSTAL_CODE] = "invalid_postal_code"
            else:
                api = VigiEauApi(async_get_clientsession(self.hass))
                try:
                    self._candidates = await api.async_search_postal_code(postal_code)
                except (VigiEauConnectionError, VigiEauError):
                    errors["base"] = "cannot_connect"
                else:
                    if not self._candidates:
                        errors["base"] = "postal_code_not_found"
                    elif len(self._candidates) == 1:
                        self._pending_location = self._candidates[0]
                        return await self.async_step_preferences()
                    else:
                        return await self.async_step_location()

        return self.async_show_form(
            step_id="postal_code",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_POSTAL_CODE): TextSelector(
                        TextSelectorConfig(autocomplete="postal-code")
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_map(self, user_input: dict[str, Any] | None = None):
        """Select exact coordinates from the Home Assistant map."""
        errors: dict[str, str] = {}
        if user_input is not None:
            selected = dict(user_input[CONF_MAP_LOCATION])
            api = VigiEauApi(async_get_clientsession(self.hass))
            try:
                location = await api.async_reverse_location(
                    float(selected["latitude"]),
                    float(selected["longitude"]),
                    location_type=LOCATION_MODE_MAP,
                )
            except (VigiEauConnectionError, VigiEauError):
                errors["base"] = "cannot_connect"
            else:
                if location is None:
                    errors["base"] = "location_not_found"
                else:
                    self._pending_location = location
                    return await self.async_step_preferences()

        return self.async_show_form(
            step_id="map",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_MAP_LOCATION,
                        default={
                            "latitude": float(self.hass.config.latitude),
                            "longitude": float(self.hass.config.longitude),
                        },
                    ): LocationSelector(LocationSelectorConfig(icon="mdi:map-marker"))
                }
            ),
            errors=errors,
        )

    async def async_step_preferences(self, user_input: dict[str, Any] | None = None):
        """Choose the water source and profile for the resolved location."""
        if user_input is not None:
            self._pending_profile = str(user_input[CONF_PROFILE])
            self._pending_water_type = str(user_input[CONF_WATER_TYPE])
            assert self._pending_location is not None
            return await self._async_location_selected(self._pending_location)

        schema = vol.Schema(
            {
                vol.Required(CONF_WATER_TYPE, default=DEFAULT_WATER_TYPE): vol.In(
                    WATER_CHOICES
                ),
                vol.Required(CONF_PROFILE, default=DEFAULT_PROFILE): vol.In(
                    PROFILE_CHOICES
                ),
            }
        )
        return self.async_show_form(step_id="preferences", data_schema=schema)

    async def async_step_location(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            index = int(user_input["location"])
            self._pending_location = self._candidates[index]
            return await self.async_step_preferences()
        choices = {
            str(index): candidate.label
            for index, candidate in enumerate(self._candidates)
        }
        return self.async_show_form(
            step_id="location",
            data_schema=vol.Schema({vol.Required("location"): vol.In(choices)}),
        )

    async def _async_location_selected(self, location: AddressCandidate):
        self._pending_location = location
        api = VigiEauApi(async_get_clientsession(self.hass))
        try:
            zones = await api.async_get_zones(location)
        except VigiEauNoActiveOrder:
            zones = []
        except VigiEauNeedPreciseLocation:
            if self._pending_location_mode == LOCATION_MODE_ADDRESS:
                return self.async_show_form(
                    step_id="address",
                    data_schema=self._address_schema(),
                    errors={"base": "address_required"},
                )
            return self.async_show_form(
                step_id="user",
                data_schema=self._location_mode_schema(),
                errors={"base": "address_required"},
            )
        except (VigiEauConnectionError, VigiEauError):
            return self.async_abort(reason="cannot_connect")

        self._pending_zones = format_zones(zones)
        matching = zones_for_water_type(self._pending_zones, self._pending_water_type)
        if len(matching) > 1:
            return await self.async_step_zone()
        zone_id = matching[0].id if len(matching) == 1 else None
        return await self._async_create_entry(zone_id)

    async def async_step_zone(self, user_input: dict[str, Any] | None = None):
        matching = zones_for_water_type(self._pending_zones, self._pending_water_type)
        if user_input is not None:
            return await self._async_create_entry(str(user_input[CONF_ZONE_ID]))
        choices = {zone.id: zone.name for zone in matching}
        return self.async_show_form(
            step_id="zone",
            data_schema=vol.Schema({vol.Required(CONF_ZONE_ID): vol.In(choices)}),
        )

    async def _async_create_entry(self, zone_id: str | None):
        assert self._pending_location is not None
        location = self._pending_location
        await self.async_set_unique_id(location.unique_key)
        self._abort_if_unique_id_configured()
        data = {
            CONF_LABEL: location.label,
            CONF_CITYCODE: location.citycode,
            CONF_LONGITUDE: location.longitude,
            CONF_LATITUDE: location.latitude,
            CONF_LOCATION_TYPE: location.location_type,
            CONF_LOCATION_MODE: self._pending_location_mode,
            CONF_PROFILE: self._pending_profile,
            CONF_WATER_TYPE: self._pending_water_type,
        }
        if zone_id:
            data[CONF_ZONE_ID] = zone_id
        return self.async_create_entry(title=location.label, data=data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return VigiEauFranceOptionsFlow(config_entry)


class VigiEauFranceOptionsFlow(config_entries.OptionsFlow):
    """Allow profile, water provenance, zone and refresh interval changes."""

    def __init__(self, config_entry) -> None:
        self.config_entry = config_entry
        self._pending: dict[str, Any] = {}
        self._zones: tuple[Zone, ...] = ()

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            self._pending = dict(user_input)
            api = VigiEauApi(async_get_clientsession(self.hass))
            location = AddressCandidate.from_config(dict(self.config_entry.data))
            try:
                zones = await api.async_get_zones(location)
            except VigiEauNoActiveOrder:
                zones = []
            except VigiEauNeedPreciseLocation:
                return self.async_abort(reason="address_required")
            except (VigiEauConnectionError, VigiEauError):
                return self.async_abort(reason="cannot_connect")
            self._zones = format_zones(zones)
            matching = zones_for_water_type(
                self._zones, str(self._pending[CONF_WATER_TYPE])
            )
            if len(matching) > 1:
                return await self.async_step_zone()
            if matching:
                self._pending[CONF_ZONE_ID] = matching[0].id
            else:
                self._pending.pop(CONF_ZONE_ID, None)
            return self.async_create_entry(title="", data=self._pending)

        current_profile = self.config_entry.options.get(
            CONF_PROFILE, self.config_entry.data.get(CONF_PROFILE, DEFAULT_PROFILE)
        )
        current_water = self.config_entry.options.get(
            CONF_WATER_TYPE,
            self.config_entry.data.get(CONF_WATER_TYPE, DEFAULT_WATER_TYPE),
        )
        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_WATER_TYPE, default=current_water): vol.In(
                    WATER_CHOICES
                ),
                vol.Required(CONF_PROFILE, default=current_profile): vol.In(
                    PROFILE_CHOICES
                ),
                vol.Required(CONF_SCAN_INTERVAL, default=current_interval): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_zone(self, user_input: dict[str, Any] | None = None):
        matching = zones_for_water_type(
            self._zones, str(self._pending[CONF_WATER_TYPE])
        )
        if user_input is not None:
            self._pending[CONF_ZONE_ID] = str(user_input[CONF_ZONE_ID])
            return self.async_create_entry(title="", data=self._pending)
        choices = {zone.id: zone.name for zone in matching}
        return self.async_show_form(
            step_id="zone",
            data_schema=vol.Schema({vol.Required(CONF_ZONE_ID): vol.In(choices)}),
        )
