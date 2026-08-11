# SPDX-FileCopyrightText: 2026 Jean-Philippe TESTART (jptstar)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Sensor platform for VigiEau France."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, NAME, VIGIEAU_WEBSITE
from .logic import (
    format_usage_entity_name,
    profile_label,
    severity_label,
    usage_icon,
    usage_key,
    usage_message_state,
    water_type_label,
)
from .models import Usage, VigiEauSnapshot

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up all VigiEau sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            VigiEauSituationSensor(coordinator, entry),
            VigiEauZoneSensor(coordinator, entry),
            VigiEauWaterTypeSensor(coordinator, entry),
            VigiEauProfileSensor(coordinator, entry),
            VigiEauOrderSensor(coordinator, entry),
            VigiEauLastUpdateSensor(coordinator, entry),
        ]
    )

    known_usage_keys: set[str] = set()

    @callback
    def _add_usage_entities() -> None:
        data: VigiEauSnapshot | None = coordinator.data
        if data is None:
            return
        new_entities: list[VigiEauUsageSensor] = []
        for usage in data.visible_usages:
            key = usage_key(usage)
            if key in known_usage_keys:
                continue
            known_usage_keys.add(key)
            new_entities.append(VigiEauUsageSensor(coordinator, entry, key, usage.name))
        if new_entities:
            async_add_entities(new_entities)

    _add_usage_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_usage_entities))


class VigiEauBaseSensor(CoordinatorEntity, SensorEntity):
    """Base entity sharing the location device."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator, entry: ConfigEntry, suffix: str, name: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = name
        self._attr_unique_id = f"{entry.unique_id}_{suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"{NAME} – {entry.title}",
            manufacturer="VigiEau",
            model="Service public – API VigiEau",
            configuration_url=VIGIEAU_WEBSITE,
        )


class VigiEauDiagnosticSensor(VigiEauBaseSensor):
    """Base class for informational entities shown in HA diagnostics."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC


class VigiEauSituationSensor(VigiEauDiagnosticSensor):
    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "situation", "Situation")
        self._attr_icon = "mdi:water-alert"

    @property
    def native_value(self) -> str:
        zone = self.coordinator.data.selected_zone
        return severity_label(zone.severity if zone else None)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        zone = data.selected_zone
        return {
            "adresse": data.location.label,
            "code_insee": data.location.citycode,
            "profil": profile_label(data.profile),
            "type_eau": water_type_label(data.water_type),
            "zone": zone.name if zone else None,
            "niveau_gravite_code": zone.severity if zone else None,
            "departement": zone.department if zone else None,
            "restrictions_affichees_par_vigieau": data.restrictions_visible,
            "nombre_de_restrictions_affichees": len(data.visible_usages),
            "mairie_peut_renforcer_les_restrictions": True,
        }


class VigiEauZoneSensor(VigiEauDiagnosticSensor):
    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "zone", "Zone")
        self._attr_icon = "mdi:map-marker-radius"

    @property
    def native_value(self) -> str | None:
        zone = self.coordinator.data.selected_zone
        return zone.name if zone else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        zone = self.coordinator.data.selected_zone
        if zone is None:
            return {}
        return {
            "id": zone.id,
            "code": zone.code or None,
            "type": zone.water_type,
            "departement": zone.department,
            "niveau_gravite": zone.severity,
            "usages_hash": zone.usages_hash,
        }


class VigiEauWaterTypeSensor(VigiEauDiagnosticSensor):
    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "type_eau", "Type d'eau")
        self._attr_icon = "mdi:water"

    @property
    def native_value(self) -> str:
        return water_type_label(self.coordinator.data.water_type)


class VigiEauProfileSensor(VigiEauDiagnosticSensor):
    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "profil", "Profil")
        self._attr_icon = "mdi:account"

    @property
    def native_value(self) -> str:
        return profile_label(self.coordinator.data.profile)


class VigiEauOrderSensor(VigiEauDiagnosticSensor):
    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "arrete", "Arrêté en vigueur")
        self._attr_icon = "mdi:file-document-outline"

    @property
    def native_value(self) -> str | None:
        zone = self.coordinator.data.selected_zone
        if zone is None:
            return None
        value = zone.order.get("dateDebutValidite")
        return str(value) if value else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        zone = self.coordinator.data.selected_zone
        if zone is None:
            return {}
        order = zone.order
        return {
            "date_debut_validite": order.get("dateDebutValidite"),
            "date_fin_validite": order.get("dateFinValidite"),
            "arrete_restriction": order.get("cheminFichier"),
            "arrete_cadre_prefectoral": order.get("cheminFichierArreteCadre"),
            "arrete_municipal": zone.municipal_order_url,
        }


class VigiEauLastUpdateSensor(VigiEauDiagnosticSensor):
    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "derniere_actualisation", "Dernière actualisation")
        self._attr_icon = "mdi:clock-outline"

    @property
    def native_value(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


class VigiEauUsageSensor(VigiEauBaseSensor):
    """One read-only entity for one VigiEau restriction card."""

    def __init__(self, coordinator, entry: ConfigEntry, key: str, initial_name: str) -> None:
        self._usage_key = key
        super().__init__(
            coordinator,
            entry,
            f"usage_{key}",
            format_usage_entity_name("Message", initial_name),
        )
        self._attr_icon = usage_icon(initial_name)

    def _usage(self) -> Usage | None:
        for usage in self.coordinator.data.visible_usages:
            if usage_key(usage) == self._usage_key:
                return usage
        return None

    @property
    def available(self) -> bool:
        return super().available and self._usage() is not None

    @property
    def native_value(self) -> str | None:
        usage = self._usage()
        if usage is None:
            return None
        return usage_message_state(usage.description)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        usage = self._usage()
        data = self.coordinator.data
        zone = data.selected_zone
        if usage is None:
            return {}
        return {
            "nom": usage.name,
            "thematique": usage.theme,
            "description": usage.description,
            "message_vigieau_integral": True,
            "longueur_message": len(usage.description),
            "id_usage": usage.id or None,
            "profil": profile_label(data.profile),
            "type_eau": water_type_label(data.water_type),
            "zone": zone.name if zone else None,
            "niveau_gravite": zone.severity if zone else None,
            "concerne_particulier": usage.concerns_individual,
            "concerne_professionnel": usage.concerns_business,
            "concerne_collectivite": usage.concerns_local_authority,
            "concerne_exploitation_agricole": usage.concerns_farm,
        }
