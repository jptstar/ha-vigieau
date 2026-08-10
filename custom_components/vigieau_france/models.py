# SPDX-FileCopyrightText: 2026 Jean-Philippe TESTART (jptstar)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Data models used by VigiEau France."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class AddressCandidate:
    """A location returned by the public address service."""

    label: str
    citycode: str
    longitude: float
    latitude: float
    location_type: str
    raw: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def unique_key(self) -> str:
        """Return a stable key for a Home Assistant config entry."""
        return f"{self.citycode}:{self.longitude:.6f}:{self.latitude:.6f}"

    def as_config(self) -> dict[str, Any]:
        """Serialize the location to config-entry-safe primitives."""
        return {
            "label": self.label,
            "citycode": self.citycode,
            "longitude": self.longitude,
            "latitude": self.latitude,
            "location_type": self.location_type,
        }

    @classmethod
    def from_config(cls, data: dict[str, Any]) -> "AddressCandidate":
        """Build a location from config entry data."""
        return cls(
            label=str(data["label"]),
            citycode=str(data["citycode"]),
            longitude=float(data["longitude"]),
            latitude=float(data["latitude"]),
            location_type=str(data.get("location_type", "housenumber")),
        )


@dataclass(frozen=True, slots=True)
class Usage:
    """A VigiEau usage/restriction card."""

    id: str
    name: str
    theme: str
    description: str
    concerns_individual: bool
    concerns_business: bool
    concerns_local_authority: bool
    concerns_farm: bool
    raw: dict[str, Any] = field(default_factory=dict, compare=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "Usage":
        """Parse an API usage without interpreting its description."""
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("nom", "")),
            theme=str(data.get("thematique", "")),
            description=str(data.get("description", "")),
            concerns_individual=bool(data.get("concerneParticulier", False)),
            concerns_business=bool(data.get("concerneEntreprise", False)),
            concerns_local_authority=bool(data.get("concerneCollectivite", False)),
            concerns_farm=bool(data.get("concerneExploitation", False)),
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class Zone:
    """A VigiEau alert zone."""

    id: str
    code: str
    name: str
    water_type: str
    severity: str
    department: str
    usages: tuple[Usage, ...]
    order: dict[str, Any]
    municipal_order_url: str | None
    usages_hash: str | None
    raw: dict[str, Any] = field(default_factory=dict, compare=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "Zone":
        """Parse a zone returned by the VigiEau API."""
        usages_data = data.get("usages") or []
        return cls(
            id=str(data.get("id", data.get("idZone", ""))),
            code=str(data.get("code", "")),
            name=str(data.get("nom", "")),
            water_type=str(data.get("type", "")),
            severity=str(data.get("niveauGravite", "")),
            department=str(data.get("departement", "")),
            usages=tuple(Usage.from_api(item) for item in usages_data if isinstance(item, dict)),
            order=dict(data.get("arrete") or {}),
            municipal_order_url=(
                str(data.get("arreteMunicipalCheminFichier"))
                if data.get("arreteMunicipalCheminFichier")
                else None
            ),
            usages_hash=(str(data.get("usagesHash")) if data.get("usagesHash") else None),
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class VigiEauSnapshot:
    """Current VigiEau view for one Home Assistant config entry."""

    location: AddressCandidate
    profile: str
    water_type: str
    zones: tuple[Zone, ...]
    selected_zone: Zone | None
    visible_usages: tuple[Usage, ...]
    restrictions_visible: bool
    needs_zone_selection: bool
