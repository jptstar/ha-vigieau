# SPDX-FileCopyrightText: 2026 Jean-Philippe TESTART (jptstar)
# SPDX-License-Identifier: GPL-3.0-or-later

"""HTTP client for official public VigiEau and address APIs."""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import COMMUNES_API_BASE, GEOCODING_API_BASE, VERSION, VIGIEAU_API_BASE
from .location import parse_address_candidates, parse_postal_candidates
from .models import AddressCandidate, Zone


class VigiEauError(Exception):
    """Base VigiEau client error."""


class VigiEauConnectionError(VigiEauError):
    """Raised when a public service cannot be reached."""


class VigiEauNoActiveOrder(VigiEauError):
    """Raised when VigiEau reports no active alert zone for the location."""


class VigiEauNeedPreciseLocation(VigiEauError):
    """Raised when a commune alone is not precise enough."""


class VigiEauInvalidResponse(VigiEauError):
    """Raised when a service returns data that cannot be consumed safely."""


class VigiEauApi:
    """Small asynchronous client around the official public endpoints."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session
        self._timeout = ClientTimeout(total=20)
        self._headers = {
            "User-Agent": f"HomeAssistant-VigiEau-France/{VERSION} (+https://github.com/jptstar/vigieau-france-ha)"
        }

    async def _get_json(self, url: str, params: dict[str, Any]) -> Any:
        try:
            async with self._session.get(
                url,
                params=params,
                headers=self._headers,
                timeout=self._timeout,
            ) as response:
                status = response.status
                if status == 404 and url.startswith(VIGIEAU_API_BASE):
                    raise VigiEauNoActiveOrder
                if status == 409 and url.startswith(VIGIEAU_API_BASE):
                    raise VigiEauNeedPreciseLocation
                if status >= 400:
                    body = await response.text()
                    raise VigiEauInvalidResponse(f"HTTP {status}: {body[:300]}")
                try:
                    return await response.json(content_type=None)
                except (ValueError, TypeError) as err:
                    raise VigiEauInvalidResponse("Invalid JSON response") from err
        except (asyncio.TimeoutError, ClientError) as err:
            raise VigiEauConnectionError(str(err)) from err

    async def async_search_addresses(
        self, query: str, limit: int = 10
    ) -> list[AddressCandidate]:
        """Search addresses through the current public Géoplateforme service."""
        payload = await self._get_json(
            f"{GEOCODING_API_BASE}/search",
            {"q": query, "index": "address", "limit": limit},
        )
        return parse_address_candidates(payload, query)

    async def async_reverse_location(
        self,
        latitude: float,
        longitude: float,
        *,
        location_type: str,
    ) -> AddressCandidate | None:
        """Resolve exact selected coordinates to the nearest French address."""
        payload = await self._get_json(
            f"{GEOCODING_API_BASE}/reverse",
            {
                "lat": latitude,
                "lon": longitude,
                "index": "address",
                "limit": 1,
            },
        )
        candidates = parse_address_candidates(
            payload,
            f"{latitude:.6f}, {longitude:.6f}",
            selected_coordinates=(longitude, latitude),
            location_type=location_type,
        )
        return candidates[0] if candidates else None

    async def async_search_postal_code(
        self, postal_code: str
    ) -> list[AddressCandidate]:
        """Return every commune matching a French postal code."""
        payload = await self._get_json(
            f"{COMMUNES_API_BASE}/communes",
            {
                "codePostal": postal_code,
                "fields": "nom,code,codesPostaux,centre",
                "format": "json",
                "geometry": "centre",
            },
        )
        return parse_postal_candidates(payload, postal_code)

    async def async_get_zones(self, location: AddressCandidate) -> list[Zone]:
        """Fetch every applicable zone; profile and water type are intentionally not sent."""
        params: dict[str, Any] = {"commune": location.citycode}
        if location.location_type != "municipality":
            params["lon"] = location.longitude
            params["lat"] = location.latitude

        payload = await self._get_json(f"{VIGIEAU_API_BASE}/zones", params)
        if isinstance(payload, dict):
            items = [payload]
        elif isinstance(payload, list):
            items = payload
        else:
            raise VigiEauInvalidResponse("Unexpected VigiEau zones payload")
        return [Zone.from_api(item) for item in items if isinstance(item, dict)]
