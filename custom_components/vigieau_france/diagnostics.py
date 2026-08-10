# SPDX-FileCopyrightText: 2026 Jean-Philippe TESTART (jptstar)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Diagnostics support for VigiEau France."""
from __future__ import annotations

from dataclasses import asdict

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

TO_REDACT = {"label", "latitude", "longitude", "address"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry):
    """Return diagnostic data while redacting the user's precise location."""
    coordinator = entry.runtime_data
    payload = {
        "config_entry": {
            "title": entry.title,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "snapshot": asdict(coordinator.data) if coordinator.data else None,
    }
    return async_redact_data(payload, TO_REDACT)
