#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Jean-Philippe TESTART (jptstar)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Build a compact VigiEau description catalogue from restrictions.csv.

Author: jptstar

The source CSV is the official VigiEau export published on data.gouv.fr.
Only message identifiers and exact descriptions are stored. The identifier uses
exactly the same whitespace normalization and SHA-256 prefix as the live audit.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path


def clean_ws(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\xa0", " ")).strip()


def message_id(value: str) -> str:
    return hashlib.sha256(clean_ws(value).encode("utf-8")).hexdigest()[:16]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    descriptions: dict[str, str] = {}
    with args.csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "usage.u.description" not in reader.fieldnames:
            raise RuntimeError("Column usage.u.description is missing from restrictions.csv")
        for row in reader:
            description = row.get("usage.u.description") or ""
            if not clean_ws(description):
                continue
            descriptions.setdefault(message_id(description), description)

    payload = [
        {"id": mid, "description": description}
        for mid, description in sorted(descriptions.items())
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Catalogue built: {len(payload)} unique descriptions -> {args.output}")


if __name__ == "__main__":
    main()
