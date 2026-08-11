# SPDX-FileCopyrightText: 2026 Jean-Philippe TESTART (jptstar)
# SPDX-License-Identifier: GPL-3.0-or-later

from custom_components.vigieau_france.location import (
    parse_address_candidates,
    parse_postal_candidates,
)


def address_payload():
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [2.359276, 48.855534]},
                "properties": {
                    "label": "1 Rue de Rivoli 75004 Paris",
                    "citycode": "75104",
                    "type": "housenumber",
                },
            }
        ],
    }


def test_direct_geocoding_candidate_uses_official_address_coordinates():
    candidates = parse_address_candidates(address_payload(), "1 rue de Rivoli Paris")
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.label == "1 Rue de Rivoli 75004 Paris"
    assert candidate.citycode == "75104"
    assert candidate.longitude == 2.359276
    assert candidate.latitude == 48.855534
    assert candidate.location_type == "housenumber"


def test_reverse_geocoding_preserves_the_exact_selected_point():
    candidates = parse_address_candidates(
        address_payload(),
        "48.856600, 2.352200",
        selected_coordinates=(2.3522, 48.8566),
        location_type="map",
    )
    candidate = candidates[0]
    assert candidate.longitude == 2.3522
    assert candidate.latitude == 48.8566
    assert candidate.location_type == "map"


def test_postal_code_candidates_use_commune_centres_and_are_sorted():
    payload = [
        {
            "nom": "Zillisheim",
            "code": "68384",
            "centre": {"type": "Point", "coordinates": [7.296, 47.696]},
        },
        {
            "nom": "Mulhouse",
            "code": "68224",
            "centre": {"type": "Point", "coordinates": [7.3255, 47.7526]},
        },
    ]
    candidates = parse_postal_candidates(payload, "68200")
    assert [candidate.label for candidate in candidates] == [
        "Mulhouse (68200)",
        "Zillisheim (68200)",
    ]
    assert candidates[0].citycode == "68224"
    assert candidates[0].location_type == "postcode"


def test_invalid_geocoding_items_are_ignored():
    assert parse_address_candidates({"features": [{}]}, "inconnue") == []
    assert parse_postal_candidates([{"nom": "Sans centre"}], "00000") == []
