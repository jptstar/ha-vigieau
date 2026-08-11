# SPDX-FileCopyrightText: 2026 Jean-Philippe TESTART (jptstar)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Independent implementation of the VigiEau display-selection rules."""
from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import replace

from .const import (
    PROFILES,
    SEVERITY_LABEL,
    SEVERITY_RANK,
    VIGILANCE_WITH_RESTRICTIONS_DEPARTMENTS,
    WATER_TYPES,
)
from .models import AddressCandidate, Usage, VigiEauSnapshot, Zone

_USAGE_ICON_RULES = (
    (("fontaine",), "mdi:fountain"),
    (("golf",), "mdi:golf"),
    (("potager", "maraichage"), "mdi:sprout"),
    (("pelouse",), "mdi:grass"),
    (("espace vert", "massif fleuri", "fleur"), "mdi:flower"),
    (("terrain de sport", "terrains de sport", "stade"), "mdi:soccer-field"),
    (("vehicule", "voiture"), "mdi:car-wash"),
    (("piscine", "baignade"), "mdi:pool"),
    (("plan d'eau", "plans d'eau", "etang", "mare"), "mdi:island"),
    (("facade", "toiture"), "mdi:home-outline"),
    (("trottoir", "surface impermeabilisee", "nettoyage"), "mdi:spray-bottle"),
    (("douche",), "mdi:shower"),
    (("jardin", "culture", "irrigation"), "mdi:sprout"),
)

_MAX_USAGE_STATE_LENGTH = 255


def restriction_rank(severity: str | None) -> int:
    """Return the rank used to order VigiEau situations."""
    return SEVERITY_RANK.get(severity or "", 0)


def severity_label(severity: str | None) -> str:
    """Return the user-facing situation label."""
    return SEVERITY_LABEL.get(severity or "", "Pas de restrictions")


def water_type_label(water_type: str) -> str:
    """Return the user-facing water provenance label."""
    return WATER_TYPES.get(water_type, water_type)


def profile_label(profile: str) -> str:
    """Return the user-facing consumer profile label."""
    return PROFILES.get(profile, profile)


def format_usage_entity_name(purpose: str, usage_name: str) -> str:
    """Put the official usage name first, followed by the entity purpose."""
    return f"{usage_name} - {purpose}"


def usage_icon(usage_name: str) -> str:
    """Return an icon matching the official VigiEau usage name."""
    normalized_name = "".join(
        character
        for character in unicodedata.normalize("NFKD", usage_name.casefold())
        if not unicodedata.combining(character)
    ).replace("’", "'")
    for keywords, icon in _USAGE_ICON_RULES:
        if any(keyword in normalized_name for keyword in keywords):
            return icon
    return "mdi:water-outline"


def usage_message_state(description: str) -> str:
    """Expose the official text as state, shortened only when HA requires it."""
    message = description.strip()
    if not message:
        return "Aucun message"
    if len(message) <= _MAX_USAGE_STATE_LENGTH:
        return message
    return f"{message[: _MAX_USAGE_STATE_LENGTH - 1].rstrip()}…"


def format_zones(zones: list[Zone] | tuple[Zone, ...]) -> tuple[Zone, ...]:
    """Sort usage cards alphabetically, then zones by descending gravity."""
    normalized = [
        replace(zone, usages=tuple(sorted(zone.usages, key=lambda usage: usage.name.casefold())))
        for zone in zones
    ]
    return tuple(sorted(normalized, key=lambda zone: restriction_rank(zone.severity), reverse=True))


def zones_for_water_type(zones: tuple[Zone, ...], water_type: str) -> tuple[Zone, ...]:
    """Return zones matching the selected water provenance."""
    return tuple(zone for zone in zones if zone.water_type == water_type)


def select_zone(
    zones: tuple[Zone, ...], water_type: str, selected_zone_id: str | None
) -> tuple[Zone | None, bool]:
    """Select a zone like the website and report if user input is needed."""
    candidates = zones_for_water_type(zones, water_type)
    if selected_zone_id:
        selected = next((zone for zone in candidates if zone.id == str(selected_zone_id)), None)
        if selected is not None:
            return selected, False
    if len(candidates) == 1:
        return candidates[0], False
    if len(candidates) > 1:
        return None, True
    return None, False


def usage_matches_profile(usage: Usage, profile: str) -> bool:
    """Return whether a restriction card applies to the selected profile."""
    if profile == "particulier":
        return usage.concerns_individual
    if profile == "entreprise":
        return usage.concerns_business
    if profile == "collectivite":
        return usage.concerns_local_authority
    if profile == "exploitation":
        return usage.concerns_farm
    return False


def show_restrictions(zone: Zone | None) -> bool:
    """Return whether the website displays restriction details for the zone."""
    if zone is None:
        return False
    if (
        zone.severity == "vigilance"
        and zone.department not in VIGILANCE_WITH_RESTRICTIONS_DEPARTMENTS
    ):
        return False
    return any(usage.theme != "Autre" for usage in zone.usages)


def build_snapshot(
    location: AddressCandidate,
    profile: str,
    water_type: str,
    zones: list[Zone] | tuple[Zone, ...],
    selected_zone_id: str | None = None,
) -> VigiEauSnapshot:
    """Build the Home Assistant view from official API data."""
    formatted = format_zones(zones)
    selected, needs_selection = select_zone(formatted, water_type, selected_zone_id)
    details_visible = show_restrictions(selected)
    visible_usages = ()
    if details_visible and selected is not None:
        visible_usages = tuple(
            usage for usage in selected.usages if usage_matches_profile(usage, profile)
        )
    return VigiEauSnapshot(
        location=location,
        profile=profile,
        water_type=water_type,
        zones=formatted,
        selected_zone=selected,
        visible_usages=visible_usages,
        restrictions_visible=details_visible,
        needs_zone_selection=needs_selection,
    )


def usage_key(usage: Usage) -> str:
    """Return a deterministic entity key without altering VigiEau text."""
    value = f"{usage.theme}\0{usage.name}".encode("utf-8")
    return hashlib.sha1(value, usedforsecurity=False).hexdigest()[:16]
