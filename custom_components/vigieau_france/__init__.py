# SPDX-FileCopyrightText: 2026 Jean-Philippe TESTART (jptstar)
# SPDX-License-Identifier: GPL-3.0-or-later

"""VigiEau France integration for Home Assistant."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up VigiEau France from a config entry."""
    from homeassistant.const import Platform
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from .api import VigiEauApi
    from .coordinator import VigiEauCoordinator

    api = VigiEauApi(async_get_clientsession(hass))
    coordinator = VigiEauCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR, Platform.BINARY_SENSOR])
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry after options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    from homeassistant.const import Platform

    return await hass.config_entries.async_unload_platforms(entry, [Platform.SENSOR, Platform.BINARY_SENSOR])
