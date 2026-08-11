# SPDX-FileCopyrightText: 2026 Jean-Philippe TESTART (jptstar)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Binary sensor platform for VigiEau France."""
from __future__ import annotations

from datetime import time
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import ATTRIBUTION, DOMAIN, VIGIEAU_WEBSITE
from .interpretation import InterpretedRule, UsageInterpretation, interpret_usage
from .logic import (
    format_usage_entity_name,
    profile_label,
    usage_icon,
    usage_key,
    water_type_label,
)
from .models import Usage, VigiEauSnapshot

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up dynamic VigiEau binary sensors."""
    coordinator = entry.runtime_data
    known: set[str] = set()
    time_sensitive_entities: list[VigiEauForbiddenNowBinarySensor] = []

    @callback
    def _add_usage_entities() -> None:
        data: VigiEauSnapshot | None = coordinator.data
        if data is None:
            return
        new_entities: list[BinarySensorEntity] = []
        for usage in data.visible_usages:
            key = usage_key(usage)
            restriction_id = f"restriction_{key}"
            if restriction_id not in known:
                known.add(restriction_id)
                new_entities.append(VigiEauRestrictionBinarySensor(coordinator, entry, key, usage.name))

            forbidden_id = f"forbidden_{key}"
            if forbidden_id not in known:
                known.add(forbidden_id)
                entity = VigiEauForbiddenNowBinarySensor(coordinator, entry, key, usage.name)
                time_sensitive_entities.append(entity)
                new_entities.append(entity)

            interpretation = interpret_usage(usage.description)
            if len(interpretation.rules) > 1:
                for index, rule in enumerate(interpretation.rules):
                    sub_id = f"forbidden_{key}_{index}"
                    if sub_id in known:
                        continue
                    known.add(sub_id)
                    entity = VigiEauForbiddenNowBinarySensor(
                        coordinator,
                        entry,
                        key,
                        usage.name,
                        rule_index=index,
                        rule_subject=rule.subject,
                    )
                    time_sensitive_entities.append(entity)
                    new_entities.append(entity)
        if new_entities:
            async_add_entities(new_entities)

    @callback
    def _minute_refresh(_now) -> None:
        for entity in tuple(time_sensitive_entities):
            if entity.hass is not None:
                entity.async_write_ha_state()

    _add_usage_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_usage_entities))
    entry.async_on_unload(async_track_time_change(hass, _minute_refresh, second=0))


class VigiEauBaseBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Base binary sensor sharing the VigiEau location device."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator, entry: ConfigEntry, suffix: str, name: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = name
        self._attr_unique_id = f"{entry.unique_id}_{suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_restrictions")},
            name=f"Restrictions VigiEau – {entry.title}",
            manufacturer="VigiEau",
            model="États binaires – interprétation prudente",
            configuration_url=VIGIEAU_WEBSITE,
            via_device=(DOMAIN, entry.entry_id),
        )


class VigiEauUsageBinarySensor(VigiEauBaseBinarySensor):
    """Base class bound to one official VigiEau usage card."""

    def __init__(self, coordinator, entry: ConfigEntry, suffix: str, key: str, name: str) -> None:
        self._usage_key = key
        super().__init__(coordinator, entry, suffix, name)

    def _usage(self) -> Usage | None:
        for usage in self.coordinator.data.visible_usages:
            if usage_key(usage) == self._usage_key:
                return usage
        return None

    @property
    def available(self) -> bool:
        return super().available and self._usage() is not None

    def _interpretation(self) -> UsageInterpretation | None:
        usage = self._usage()
        return interpret_usage(usage.description) if usage else None

    def _common_attributes(self) -> dict[str, Any]:
        usage = self._usage()
        data = self.coordinator.data
        zone = data.selected_zone
        if usage is None:
            return {}
        interpretation = interpret_usage(usage.description)
        return {
            "nom": usage.name,
            "thematique": usage.theme,
            "message_vigieau": usage.description,
            "interpretation": interpretation.kind.value,
            "profil": profile_label(data.profile),
            "type_eau": water_type_label(data.water_type),
            "zone": zone.name if zone else None,
            "niveau_gravite": zone.severity if zone else None,
        }


class VigiEauRestrictionBinarySensor(VigiEauUsageBinarySensor):
    """Whether the official message clearly contains a restriction."""

    def __init__(self, coordinator, entry: ConfigEntry, key: str, usage_name: str) -> None:
        super().__init__(
            coordinator,
            entry,
            f"restriction_{key}",
            key,
            format_usage_entity_name("Restriction", usage_name),
        )
        self._attr_icon = usage_icon(usage_name)

    @property
    def is_on(self) -> bool | None:
        interpretation = self._interpretation()
        return interpretation.restriction if interpretation else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = self._common_attributes()
        attrs["semantique"] = "ON = une restriction est explicitement présente dans le message VigiEau"
        return attrs


class VigiEauForbiddenNowBinarySensor(VigiEauUsageBinarySensor):
    """Whether a deterministic official rule forbids the use right now."""

    def __init__(self, coordinator, entry: ConfigEntry, key: str, usage_name: str, *, rule_index: int | None = None, rule_subject: str | None = None) -> None:
        self._rule_index = rule_index
        self._rule_subject = rule_subject
        suffix = f"interdit_maintenant_{key}"
        name = format_usage_entity_name("Interdit maintenant", usage_name)
        if rule_index is not None:
            suffix += f"_{rule_index}"
            name = format_usage_entity_name("Interdit maintenant", rule_subject or usage_name)
        super().__init__(coordinator, entry, suffix, key, name)
        self._attr_icon = usage_icon(rule_subject or usage_name)

    def _selected_rule(self) -> tuple[UsageInterpretation | None, InterpretedRule | None]:
        interpretation = self._interpretation()
        if interpretation is None:
            return None, None
        if self._rule_index is None:
            return interpretation, None
        if self._rule_index >= len(interpretation.rules):
            return interpretation, None
        return interpretation, interpretation.rules[self._rule_index]

    @property
    def is_on(self) -> bool | None:
        interpretation, rule = self._selected_rule()
        if interpretation is None:
            return None
        now: time = dt_util.now().time().replace(second=0, microsecond=0)
        if self._rule_index is None:
            return interpretation.forbidden_at(now)
        if rule is None:
            return None
        return rule.forbidden_at(now)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = self._common_attributes()
        interpretation, rule = self._selected_rule()
        attrs["semantique"] = (
            "ON = interdit maintenant; OFF = explicitement non interdit maintenant; "
            "unknown = le texte ne permet pas une conclusion sûre"
        )
        if rule is not None:
            attrs["sous_usage"] = rule.subject
            attrs["type_regle"] = rule.kind.value
            attrs["plages_interdites"] = [window.label for window in rule.windows]
        elif interpretation is not None:
            attrs["type_regle"] = interpretation.kind.value
            attrs["plages_interdites"] = [
                window.label for item in interpretation.rules for window in item.windows
            ]
        return attrs
