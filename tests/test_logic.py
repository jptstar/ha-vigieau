# SPDX-FileCopyrightText: 2026 Jean-Philippe TESTART (jptstar)
# SPDX-License-Identifier: GPL-3.0-or-later

from custom_components.vigieau_france.logic import (
    build_snapshot,
    format_usage_entity_name,
    format_zones,
    restriction_rank,
    severity_label,
    show_restrictions,
    usage_message_state,
    usage_matches_profile,
)
from custom_components.vigieau_france.models import AddressCandidate, Usage, Zone


def usage(name="Arrosage des pelouses", theme="Arroser", **flags):
    return Usage(
        id="1",
        name=name,
        theme=theme,
        description=flags.pop("description", "Interdit."),
        concerns_individual=flags.pop("individual", True),
        concerns_business=flags.pop("business", False),
        concerns_local_authority=flags.pop("authority", False),
        concerns_farm=flags.pop("farm", False),
    )


def zone(zone_id, water_type, severity, department="68", usages=()):
    return Zone(
        id=str(zone_id),
        code="",
        name=f"Zone {zone_id}",
        water_type=water_type,
        severity=severity,
        department=department,
        usages=tuple(usages),
        order={},
        municipal_order_url=None,
        usages_hash=None,
    )


def location():
    return AddressCandidate("Adresse de test", "00000", 1.0, 2.0, "housenumber")


def test_severity_ranking_and_labels():
    assert restriction_rank("crise") == 4
    assert restriction_rank("alerte_renforcee") == 3
    assert restriction_rank("alerte") == 2
    assert restriction_rank("vigilance") == 1
    assert restriction_rank("future_value") == 0
    assert severity_label("alerte_renforcee") == "alerte renforcée"
    assert severity_label(None) == "Pas de restrictions"


def test_usage_entity_names_put_the_usage_before_the_purpose():
    usage_name = "Alimentation des fontaines publiques et privées"
    assert format_usage_entity_name("Message", usage_name) == f"{usage_name} - Message"
    assert (
        format_usage_entity_name("Restriction", usage_name)
        == f"{usage_name} - Restriction"
    )
    assert (
        format_usage_entity_name("Interdit maintenant", usage_name)
        == f"{usage_name} - Interdit maintenant"
    )


def test_usage_message_state_is_short_and_preserves_empty_messages():
    assert usage_message_state("Texte officiel très long") == "Disponible"
    assert usage_message_state("   ") == "Non disponible"


def test_zones_are_sorted_by_gravity_and_usages_by_name():
    zones = format_zones([
        zone(1, "AEP", "alerte", usages=[usage("Z usage"), usage("A usage")]),
        zone(2, "SUP", "crise"),
    ])
    assert [z.id for z in zones] == ["2", "1"]
    assert [u.name for u in zones[1].usages] == ["A usage", "Z usage"]


def test_profile_filter_uses_structured_flags_only():
    item = usage(individual=False, business=True)
    assert not usage_matches_profile(item, "particulier")
    assert usage_matches_profile(item, "entreprise")


def test_vigilance_details_match_frontend_rule():
    assert not show_restrictions(zone(1, "AEP", "vigilance", department="68", usages=[usage()]))
    assert show_restrictions(zone(1, "AEP", "vigilance", department="59", usages=[usage()]))
    assert show_restrictions(zone(1, "AEP", "alerte", department="68", usages=[usage()]))


def test_multiple_resources_require_selection():
    snapshot = build_snapshot(
        location(), "particulier", "SUP",
        [zone(1, "SUP", "alerte"), zone(2, "SUP", "crise")],
    )
    assert snapshot.selected_zone is None
    assert snapshot.needs_zone_selection


def test_selected_resource_controls_visible_restrictions():
    snapshot = build_snapshot(
        location(), "particulier", "SUP",
        [
            zone(1, "SUP", "alerte", usages=[usage("Pelouse")]),
            zone(2, "SUP", "crise", usages=[usage("Piscine")]),
        ],
        selected_zone_id="1",
    )
    assert snapshot.selected_zone.id == "1"
    assert [u.name for u in snapshot.visible_usages] == ["Pelouse"]


def test_long_official_description_is_preserved_exactly():
    description = "Restriction officielle. " * 40
    item = usage(description=description)
    z = zone(1, "AEP", "alerte", usages=[item])
    snapshot = build_snapshot(location(), "particulier", "AEP", [z])
    assert snapshot.visible_usages[0].description == description
