# SPDX-FileCopyrightText: 2026 Jean-Philippe TESTART (jptstar)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for conservative VigiEau binary interpretation."""
from __future__ import annotations

from datetime import time

from custom_components.vigieau_france.interpretation import InterpretationKind, interpret_usage


def test_total_ban_is_always_forbidden() -> None:
    result = interpret_usage("Interdit")
    assert result.kind == InterpretationKind.TOTAL_BAN
    assert result.restriction is True
    assert result.forbidden_at(time(3, 0)) is True
    assert result.forbidden_at(time(18, 0)) is True


def test_simple_time_ban() -> None:
    result = interpret_usage("Interdiction de 8h à 20h")
    assert result.kind == InterpretationKind.TIME_BAN
    assert result.restriction is True
    assert result.forbidden_at(time(7, 59)) is False
    assert result.forbidden_at(time(8, 0)) is True
    assert result.forbidden_at(time(19, 59)) is True
    assert result.forbidden_at(time(20, 0)) is False


def test_time_ban_crossing_midnight() -> None:
    result = interpret_usage("Interdiction de 20h à 8h")
    assert result.kind == InterpretationKind.TIME_BAN
    assert result.forbidden_at(time(21, 0)) is True
    assert result.forbidden_at(time(3, 0)) is True
    assert result.forbidden_at(time(12, 0)) is False


def test_multiple_time_ban_windows() -> None:
    result = interpret_usage("Interdiction de 8h à 12h et de 14h à 20h")
    assert result.kind == InterpretationKind.TIME_BAN
    assert result.restriction is True
    assert result.forbidden_at(time(7, 59)) is False
    assert result.forbidden_at(time(8, 0)) is True
    assert result.forbidden_at(time(12, 0)) is False
    assert result.forbidden_at(time(14, 0)) is True
    assert result.forbidden_at(time(20, 0)) is False
    assert [window.label for window in result.rules[0].windows] == [
        "08:00–12:00",
        "14:00–20:00",
    ]


def test_multiple_time_windows_with_distinct_subjects_stay_unknown() -> None:
    result = interpret_usage(
        "Interdit de 8h à 12h pour les pelouses et de 14h à 20h pour les massifs"
    )
    assert result.kind == InterpretationKind.CONDITIONAL
    assert result.restriction is True
    assert result.forbidden_at(time(10, 0)) is None


def test_mixed_prohibition_and_permission_stays_unknown() -> None:
    result = interpret_usage("Interdit de 8h à 12h et autorisé de 14h à 20h")
    assert result.kind == InterpretationKind.CONDITIONAL
    assert result.restriction is True
    assert result.forbidden_at(time(10, 0)) is None


def test_lawn_and_other_uses_are_not_merged() -> None:
    result = interpret_usage(
        "Arrosage des pelouses interdit.\n"
        "Interdiction horaire de 8h à 20h pour les autres usages."
    )
    assert result.kind == InterpretationKind.MIXED
    assert result.restriction is True
    assert result.forbidden_at(time(3, 0)) is None
    assert len(result.rules) == 2
    lawn, others = result.rules
    assert lawn.subject == "Arrosage des pelouses"
    assert lawn.forbidden_at(time(3, 0)) is True
    assert lawn.forbidden_at(time(15, 0)) is True
    assert others.subject == "Autres usages"
    assert others.forbidden_at(time(3, 0)) is False
    assert others.forbidden_at(time(15, 0)) is True


def test_conditional_ban_never_becomes_false_permission() -> None:
    result = interpret_usage("Interdit sauf pour les jeunes plantations de moins de 2 ans")
    assert result.kind == InterpretationKind.CONDITIONAL
    assert result.restriction is True
    assert result.forbidden_at(time(12, 0)) is None


def test_unknown_message_is_unknown_not_allowed() -> None:
    result = interpret_usage("Voir détails dans l'arrêté préfectoral.")
    assert result.kind == InterpretationKind.UNKNOWN
    assert result.restriction is None
    assert result.forbidden_at(time(12, 0)) is None
