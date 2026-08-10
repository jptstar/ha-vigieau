#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Jean-Philippe TESTART (jptstar)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Exhaustive commune/postal-code audit of the public VigiEau API.

Author: jptstar

This development tool is deliberately kept outside the Home Assistant runtime.
It queries the official French commune API to obtain every current INSEE commune
code and postal code, then queries the public VigiEau /zones endpoint exactly at
commune level. When VigiEau returns HTTP 409 because a commune spans several
zones, the tool records that fact and also tests the commune centre as one
representative precise location.

The national VigiEau restrictions export remains the exhaustive source for the
catalogue of active official restriction messages. This geographic audit checks
how the live public API resolves communes and detects messages that are newer
than the bundled catalogue.
"""
from __future__ import annotations

import argparse
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import random
import re
import threading
import time
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

GEO_URL = "https://geo.api.gouv.fr/communes"
VIGIEAU_URL = "https://api.vigieau.gouv.fr/api/zones"
USER_AGENT = "vigieau-france-ha-audit/0.2.0 (+https://github.com/jptstar/vigieau-france-ha)"
RETRYABLE_HTTP = {429, 500, 502, 503, 504}


def clean_ws(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\xa0", " ")).strip()


def message_id(value: str) -> str:
    return hashlib.sha256(clean_ws(value).encode("utf-8")).hexdigest()[:16]


class RateLimiter:
    """Simple process-wide request limiter shared by worker threads."""

    def __init__(self, requests_per_second: float) -> None:
        self._interval = 0.0 if requests_per_second <= 0 else 1.0 / requests_per_second
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        if self._interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next - now)
            if delay:
                time.sleep(delay)
            now = time.monotonic()
            self._next = max(self._next, now) + self._interval


@dataclass(slots=True)
class HttpResult:
    status: int
    payload: Any
    attempts: int


def get_json(
    url: str,
    params: dict[str, Any],
    limiter: RateLimiter,
    timeout: int = 30,
    retries: int = 4,
) -> HttpResult:
    target = f"{url}?{urlencode(params, doseq=True)}"
    last_status = 0
    last_payload: Any = {"message": "unknown error"}

    for attempt in range(1, retries + 1):
        limiter.wait()
        request = Request(target, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed official URLs
                return HttpResult(response.status, json.load(response), attempt)
        except HTTPError as err:
            last_status = err.code
            try:
                last_payload = json.loads(err.read().decode("utf-8", errors="replace"))
            except Exception:
                last_payload = {"message": str(err)}
            if err.code not in RETRYABLE_HTTP or attempt >= retries:
                return HttpResult(last_status, last_payload, attempt)
        except (URLError, TimeoutError, OSError) as err:
            last_status = 0
            last_payload = {"message": str(err)}
            if attempt >= retries:
                return HttpResult(last_status, last_payload, attempt)

        time.sleep(min(8.0, (2 ** (attempt - 1)) + random.random()))

    return HttpResult(last_status, last_payload, retries)


def normalize_zones(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and "id" in payload:
        return [payload]
    return []


def extract_zone_summary(zone: dict[str, Any]) -> dict[str, Any]:
    usages = zone.get("usages") if isinstance(zone.get("usages"), list) else []
    return {
        "id": zone.get("id"),
        "code": zone.get("code"),
        "nom": zone.get("nom"),
        "type": zone.get("type"),
        "niveauGravite": zone.get("niveauGravite"),
        "departement": zone.get("departement"),
        "usage_count": len(usages),
    }


def extract_messages(zones: Iterable[dict[str, Any]]) -> tuple[list[str], dict[str, str]]:
    ids: set[str] = set()
    exact: dict[str, str] = {}
    for zone in zones:
        usages = zone.get("usages") if isinstance(zone.get("usages"), list) else []
        for usage in usages:
            if not isinstance(usage, dict):
                continue
            description = usage.get("description")
            if not isinstance(description, str) or not clean_ws(description):
                continue
            mid = message_id(description)
            ids.add(mid)
            exact.setdefault(mid, description)
    return sorted(ids), exact


def load_catalogue(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    result: set[str] = set()
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("id"), str):
                result.add(item["id"])
            elif isinstance(item.get("description"), str):
                result.add(message_id(item["description"]))
    return result


def load_communes(limiter: RateLimiter) -> list[dict[str, Any]]:
    result = get_json(
        GEO_URL,
        {
            "fields": "nom,code,codeDepartement,codesPostaux,centre",
            "format": "json",
            "geometry": "centre",
        },
        limiter,
        timeout=90,
    )
    if result.status != 200 or not isinstance(result.payload, list):
        raise RuntimeError(f"Impossible de charger les communes: HTTP {result.status} {result.payload}")
    return result.payload


def audit_commune(
    commune: dict[str, Any],
    limiter: RateLimiter,
    catalogue_ids: set[str],
) -> dict[str, Any]:
    code = str(commune.get("code", ""))
    name = str(commune.get("nom", ""))
    department = str(commune.get("codeDepartement", ""))
    postal_codes = [str(x) for x in (commune.get("codesPostaux") or [])]

    response = get_json(VIGIEAU_URL, {"commune": code}, limiter)
    result: dict[str, Any] = {
        "code": code,
        "nom": name,
        "departement": department,
        "codesPostaux": postal_codes,
        "commune_status": response.status,
        "commune_attempts": response.attempts,
        "multi_zone": response.status == 409,
        "point_status": None,
        "point_attempts": None,
        "zone_count": None,
        "zones": [],
        "types_eau": [],
        "message_ids": [],
        "unknown_messages": [],
        "error": None,
    }

    zones: list[dict[str, Any]] = []
    if response.status == 200:
        zones = normalize_zones(response.payload)
    elif response.status == 409:
        centre = commune.get("centre") or {}
        coords = centre.get("coordinates") or []
        if len(coords) >= 2:
            point_response = get_json(
                VIGIEAU_URL,
                {"commune": code, "lon": coords[0], "lat": coords[1]},
                limiter,
            )
            result["point_status"] = point_response.status
            result["point_attempts"] = point_response.attempts
            if point_response.status == 200:
                zones = normalize_zones(point_response.payload)
            else:
                result["error"] = point_response.payload
        else:
            result["error"] = {"message": "Centre de commune absent"}
    else:
        result["error"] = response.payload

    if zones:
        result["zone_count"] = len(zones)
        result["zones"] = [extract_zone_summary(zone) for zone in zones]
        result["types_eau"] = sorted(
            {str(zone.get("type", "")) for zone in zones if zone.get("type")}
        )
        mids, exact = extract_messages(zones)
        result["message_ids"] = mids
        if catalogue_ids:
            result["unknown_messages"] = [
                {"id": mid, "description": exact[mid]}
                for mid in mids
                if mid not in catalogue_ids
            ]
    elif result["zone_count"] is None and response.status == 200:
        result["zone_count"] = 0

    return result


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                yield item


def build_summary(results_path: Path, output_dir: Path, catalogue_ids: set[str]) -> None:
    rows = list(iter_jsonl(results_path))
    output_dir.mkdir(parents=True, exist_ok=True)

    status_counts: dict[str, int] = {}
    point_status_counts: dict[str, int] = {}
    postal: dict[str, dict[str, Any]] = {}
    unique_zones: dict[str, dict[str, Any]] = {}
    api_message_ids: set[str] = set()
    unknown_messages: dict[str, dict[str, Any]] = {}

    for row in rows:
        status_key = str(row.get("commune_status"))
        status_counts[status_key] = status_counts.get(status_key, 0) + 1
        if row.get("point_status") is not None:
            point_key = str(row.get("point_status"))
            point_status_counts[point_key] = point_status_counts.get(point_key, 0) + 1

        for cp in row.get("codesPostaux") or []:
            item = postal.setdefault(
                str(cp),
                {
                    "code_postal": str(cp),
                    "communes": [],
                    "codes_insee": [],
                    "multi_zone_communes": 0,
                    "api_errors": 0,
                    "types_eau": set(),
                },
            )
            item["communes"].append(str(row.get("nom", "")))
            item["codes_insee"].append(str(row.get("code", "")))
            if row.get("multi_zone"):
                item["multi_zone_communes"] += 1
            if row.get("commune_status") not in (200, 409):
                item["api_errors"] += 1
            item["types_eau"].update(str(x) for x in (row.get("types_eau") or []))

        for zone in row.get("zones") or []:
            key = str(zone.get("code") or zone.get("id") or "")
            if key:
                unique_zones.setdefault(key, zone)

        for mid in row.get("message_ids") or []:
            api_message_ids.add(str(mid))

        for item in row.get("unknown_messages") or []:
            mid = str(item.get("id", ""))
            if not mid:
                continue
            entry = unknown_messages.setdefault(
                mid,
                {
                    "id": mid,
                    "description": item.get("description", ""),
                    "occurrences": 0,
                    "communes_exemples": [],
                },
            )
            entry["occurrences"] += 1
            sample = f"{row.get('code')} {row.get('nom')}"
            if len(entry["communes_exemples"]) < 10 and sample not in entry["communes_exemples"]:
                entry["communes_exemples"].append(sample)

    commune_csv = output_dir / "communes.csv"
    with commune_csv.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "code_insee", "nom", "departement", "codes_postaux", "status_commune",
            "multi_zone", "status_point_centre", "zone_count", "types_eau", "api_error",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in sorted(rows, key=lambda x: str(x.get("code", ""))):
            writer.writerow({
                "code_insee": row.get("code", ""),
                "nom": row.get("nom", ""),
                "departement": row.get("departement", ""),
                "codes_postaux": " | ".join(row.get("codesPostaux") or []),
                "status_commune": row.get("commune_status", ""),
                "multi_zone": row.get("multi_zone", False),
                "status_point_centre": row.get("point_status", ""),
                "zone_count": row.get("zone_count", ""),
                "types_eau": " | ".join(row.get("types_eau") or []),
                "api_error": json.dumps(row.get("error"), ensure_ascii=False) if row.get("error") else "",
            })

    postal_csv = output_dir / "codes_postaux.csv"
    with postal_csv.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "code_postal", "nombre_communes", "communes", "codes_insee",
            "multi_zone_communes", "api_errors", "types_eau",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for cp, item in sorted(postal.items()):
            writer.writerow({
                "code_postal": cp,
                "nombre_communes": len(item["codes_insee"]),
                "communes": " | ".join(item["communes"]),
                "codes_insee": " | ".join(item["codes_insee"]),
                "multi_zone_communes": item["multi_zone_communes"],
                "api_errors": item["api_errors"],
                "types_eau": " | ".join(sorted(item["types_eau"])),
            })

    unknown_path = output_dir / "messages_api_absents_du_catalogue.json"
    unknown_path.write_text(
        json.dumps(sorted(unknown_messages.values(), key=lambda x: x["id"]), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = {
        "communes_auditees": len(rows),
        "codes_postaux_distincts": len(postal),
        "communes_multi_zones_http_409": sum(1 for row in rows if row.get("multi_zone")),
        "statuts_requete_commune": status_counts,
        "statuts_point_centre_pour_409": point_status_counts,
        "zones_distinctes_observees": len(unique_zones),
        "messages_distincts_observes_via_api": len(api_message_ids),
        "messages_catalogue_reference": len(catalogue_ids),
        "messages_api_absents_du_catalogue": len(unknown_messages),
        "communes_en_erreur": sum(
            1 for row in rows
            if row.get("commune_status") not in (200, 409)
            or (row.get("multi_zone") and row.get("point_status") not in (200, None))
        ),
    }
    (output_dir / "resume.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    report = [
        "# Audit géographique national VigiEau",
        "",
        "Auteur : jptstar",
        "",
        f"- Communes auditées : **{summary['communes_auditees']}**",
        f"- Codes postaux distincts : **{summary['codes_postaux_distincts']}**",
        f"- Communes nécessitant une localisation précise (HTTP 409) : **{summary['communes_multi_zones_http_409']}**",
        f"- Zones distinctes observées : **{summary['zones_distinctes_observees']}**",
        f"- Messages distincts observés via l'API : **{summary['messages_distincts_observes_via_api']}**",
        f"- Messages nouveaux par rapport au catalogue embarqué : **{summary['messages_api_absents_du_catalogue']}**",
        f"- Communes/requêtes restant en erreur : **{summary['communes_en_erreur']}**",
        "",
        "## Principe",
        "",
        "Une réponse HTTP 409 au niveau commune n'est pas considérée comme une erreur métier : ",
        "elle indique qu'une adresse/coordonnée précise est nécessaire. Le centre de la commune ",
        "est alors interrogé uniquement comme point représentatif. Le catalogue national des ",
        "messages officiels est vérifié séparément à partir de l'export VigiEau.",
    ]
    (output_dir / "RAPPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("audit/vigieau_communes_audit.jsonl"))
    parser.add_argument("--summary-dir", type=Path, default=Path("audit"))
    parser.add_argument("--catalogue", type=Path, default=Path("tests/fixtures/vigieau_descriptions_2026-08-08.json"))
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--rps", type=float, default=5.0, help="Global maximum request rate")
    parser.add_argument("--max-communes", type=int, default=0, help="0 = all communes")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    limiter = RateLimiter(args.rps)
    catalogue_ids = load_catalogue(args.catalogue)
    communes = load_communes(limiter)
    communes.sort(key=lambda item: str(item.get("code", "")))

    if args.max_communes > 0:
        communes = communes[: args.max_communes]

    completed: set[str] = set()
    if args.resume and args.output.exists():
        completed = {str(item.get("code", "")) for item in iter_jsonl(args.output)}
    pending = [item for item in communes if str(item.get("code", "")) not in completed]

    print(
        f"Communes chargées: {len(communes)} | déjà présentes: {len(completed)} | "
        f"à auditer: {len(pending)} | limite globale: {args.rps:g} req/s"
    )

    mode = "a" if args.resume and args.output.exists() else "w"
    with args.output.open(mode, encoding="utf-8") as handle:
        with ThreadPoolExecutor(max_workers=max(1, min(args.concurrency, 8))) as pool:
            futures = {
                pool.submit(audit_commune, commune, limiter, catalogue_ids): commune
                for commune in pending
            }
            for index, future in enumerate(as_completed(futures), start=1):
                commune = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = {
                        "code": str(commune.get("code", "")),
                        "nom": str(commune.get("nom", "")),
                        "departement": str(commune.get("codeDepartement", "")),
                        "codesPostaux": [str(x) for x in (commune.get("codesPostaux") or [])],
                        "commune_status": -1,
                        "multi_zone": False,
                        "point_status": None,
                        "zone_count": None,
                        "zones": [],
                        "types_eau": [],
                        "message_ids": [],
                        "unknown_messages": [],
                        "error": {"message": repr(exc)},
                    }
                handle.write(json.dumps(result, ensure_ascii=False) + "\n")
                handle.flush()
                if index % 100 == 0 or index == len(pending):
                    print(f"{index}/{len(pending)} nouvelles communes analysées")

    build_summary(args.output, args.summary_dir, catalogue_ids)
    print(f"Audit terminé. Résultats: {args.summary_dir}")


if __name__ == "__main__":
    main()
