# SPDX-FileCopyrightText: 2026 Jean-Philippe TESTART (jptstar)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Pure helpers for converting public geocoding responses into locations."""

from __future__ import annotations

from typing import Any

from .models import AddressCandidate


def parse_address_candidates(
    payload: Any,
    query: str,
    *,
    selected_coordinates: tuple[float, float] | None = None,
    location_type: str | None = None,
) -> list[AddressCandidate]:
    """Parse a GeoJSON geocoding response without losing selected coordinates."""
    features = payload.get("features", []) if isinstance(payload, dict) else []
    candidates: list[AddressCandidate] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates") or []
        if len(coordinates) < 2 or not properties.get("citycode"):
            continue
        longitude, latitude = (
            selected_coordinates
            if selected_coordinates is not None
            else (float(coordinates[0]), float(coordinates[1]))
        )
        candidates.append(
            AddressCandidate(
                label=str(properties.get("label") or properties.get("name") or query),
                citycode=str(properties["citycode"]),
                longitude=float(longitude),
                latitude=float(latitude),
                location_type=location_type or str(properties.get("type", "")),
                raw=feature,
            )
        )
    return candidates


def parse_postal_candidates(payload: Any, postal_code: str) -> list[AddressCandidate]:
    """Parse communes matching a French postal code using their official centre."""
    if not isinstance(payload, list):
        return []
    candidates: list[AddressCandidate] = []
    for commune in payload:
        if not isinstance(commune, dict):
            continue
        centre = commune.get("centre") or {}
        coordinates = centre.get("coordinates") or []
        if len(coordinates) < 2 or not commune.get("code"):
            continue
        name = str(commune.get("nom") or commune["code"])
        candidates.append(
            AddressCandidate(
                label=f"{name} ({postal_code})",
                citycode=str(commune["code"]),
                longitude=float(coordinates[0]),
                latitude=float(coordinates[1]),
                location_type="postcode",
                raw=commune,
            )
        )
    return sorted(candidates, key=lambda candidate: candidate.label.casefold())
