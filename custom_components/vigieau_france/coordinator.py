"""Data update coordinator for VigiEau France."""
from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    VigiEauApi,
    VigiEauConnectionError,
    VigiEauError,
    VigiEauNeedPreciseLocation,
    VigiEauNoActiveOrder,
)
from .const import (
    CONF_PROFILE,
    CONF_SCAN_INTERVAL,
    CONF_WATER_TYPE,
    CONF_ZONE_ID,
    DEFAULT_PROFILE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_WATER_TYPE,
    DOMAIN,
)
from .logic import build_snapshot
from .models import AddressCandidate, VigiEauSnapshot

_LOGGER = logging.getLogger(__name__)


class VigiEauCoordinator(DataUpdateCoordinator[VigiEauSnapshot]):
    """Coordinate a single VigiEau poll for all entities."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: VigiEauApi) -> None:
        self.entry = entry
        self.api = api
        minutes = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(minutes=minutes),
            always_update=False,
        )

    async def _async_update_data(self) -> VigiEauSnapshot:
        location = AddressCandidate.from_config(dict(self.entry.data))
        profile = str(self.entry.options.get(CONF_PROFILE, self.entry.data.get(CONF_PROFILE, DEFAULT_PROFILE)))
        water_type = str(
            self.entry.options.get(CONF_WATER_TYPE, self.entry.data.get(CONF_WATER_TYPE, DEFAULT_WATER_TYPE))
        )
        zone_id = self.entry.options.get(CONF_ZONE_ID, self.entry.data.get(CONF_ZONE_ID))

        try:
            zones = await self.api.async_get_zones(location)
        except VigiEauNoActiveOrder:
            zones = []
        except VigiEauNeedPreciseLocation as err:
            raise UpdateFailed("La localisation doit être précisée avec une adresse.") from err
        except VigiEauConnectionError as err:
            raise UpdateFailed(f"Service VigiEau indisponible: {err}") from err
        except VigiEauError as err:
            raise UpdateFailed(f"Réponse VigiEau inexploitable: {err}") from err

        snapshot = build_snapshot(location, profile, water_type, zones, str(zone_id) if zone_id else None)
        if snapshot.needs_zone_selection:
            raise UpdateFailed(
                "Plusieurs ressources correspondent au type d'eau sélectionné; choisissez une zone dans les options."
            )
        return snapshot
