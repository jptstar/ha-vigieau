"""HTTP client for official public VigiEau and address APIs."""
from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import ADDRESS_API_BASE, VERSION, VIGIEAU_API_BASE
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
            "User-Agent": f"HomeAssistant-VigiEau-France/{VERSION} (+https://github.com/jptstar/ha-vigieau)"
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
                if status == 404:
                    raise VigiEauNoActiveOrder
                if status == 409:
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

    async def async_search_addresses(self, query: str, limit: int = 10) -> list[AddressCandidate]:
        """Search the public address service with the same broad search style as VigiEau."""
        payload = await self._get_json(
            f"{ADDRESS_API_BASE}/search/", {"q": query, "limit": limit}
        )
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
            candidates.append(
                AddressCandidate(
                    label=str(properties.get("label") or properties.get("name") or query),
                    citycode=str(properties["citycode"]),
                    longitude=float(coordinates[0]),
                    latitude=float(coordinates[1]),
                    location_type=str(properties.get("type", "")),
                    raw=feature,
                )
            )
        return candidates

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
