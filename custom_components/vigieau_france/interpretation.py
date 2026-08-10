"""Conservative interpretation helpers for optional Home Assistant binary sensors.

The official VigiEau text is always the reference. This module never changes
or replaces that text. It only derives a binary state when the wording is
sufficiently explicit to do so safely.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from enum import StrEnum
import re


class InterpretationKind(StrEnum):
    NO_RESTRICTION = "no_restriction"
    ADVISORY = "advisory"
    TOTAL_BAN = "total_ban"
    TIME_BAN = "time_ban"
    CONDITIONAL = "conditional"
    MIXED = "mixed"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class TimeWindow:
    start: time
    end: time

    def contains(self, value: time) -> bool:
        current = value.hour * 60 + value.minute
        start = self.start.hour * 60 + self.start.minute
        end = self.end.hour * 60 + self.end.minute
        if start == end:
            return True
        if start < end:
            return start <= current < end
        return current >= start or current < end

    @property
    def label(self) -> str:
        return f"{self.start:%H:%M}–{self.end:%H:%M}"


@dataclass(frozen=True, slots=True)
class InterpretedRule:
    subject: str
    kind: InterpretationKind
    restriction: bool | None
    windows: tuple[TimeWindow, ...] = ()

    def forbidden_at(self, value: time) -> bool | None:
        if self.kind == InterpretationKind.TOTAL_BAN:
            return True
        if self.kind == InterpretationKind.TIME_BAN:
            return any(window.contains(value) for window in self.windows)
        if self.kind in (InterpretationKind.NO_RESTRICTION, InterpretationKind.ADVISORY):
            return False
        return None


@dataclass(frozen=True, slots=True)
class UsageInterpretation:
    kind: InterpretationKind
    restriction: bool | None
    rules: tuple[InterpretedRule, ...]
    source_text: str

    def forbidden_at(self, value: time) -> bool | None:
        if len(self.rules) != 1:
            return None
        return self.rules[0].forbidden_at(value)


_SPACE_RE = re.compile(r"\s+")
_TRAILING_PUNCT_RE = re.compile(r"[\s.;,:]+$")
_CONDITIONAL_MARKERS = (
    " sauf ", " à l'exception ", " a l'exception ", " exception ",
    " sous réserve ", " sous reserve ", " sur décision ", " sur decision ",
    " dans la mesure ", " lorsque ", " uniquement ", " seulement ",
    " après accord ", " apres accord ", " après autorisation ", " apres autorisation ",
    " peut être interdit ", " peuvent être interdits ", " possible sur ",
)
_ADVISORY_PREFIXES = (
    "sensibiliser ", "sensibilisation ", "incitation ", "il est recommandé ",
    "il est recommande ", "le préfet invite ", "le prefet invite ",
    "application des règles de bon usage", "application des regles de bon usage",
)
_NO_RESTRICTION_EXACT = {
    "autorisé", "autorise", "autorisée", "autorisee", "sans interdiction",
    "aucune restriction", "pas de restriction", "pas de restrictions",
}
_TOTAL_BAN_EXACT = {
    "interdit", "interdite", "interdits", "interdites", "interdiction",
    "interdiction totale", "interdiction stricte", "interdiction d'arroser",
    "interdiction d’arroser", "interdiction d'arrosage", "interdiction d’arrosage",
    "lavage interdit", "prélèvements interdits", "prelevements interdits",
    "toute usage est interdit",
}
_BAN_TOKEN_RE = re.compile(r"\b(?:interdit(?:e|es|s)?|interdiction)\b", re.IGNORECASE)
_TIME_TOKEN_RE = re.compile(r"\b(?:de|entre)\s*\d{1,2}\s*(?:h|:|heures?)", re.IGNORECASE)
_DATE_OR_DAY_RE = re.compile(
    r"\b(?:du\s+\d{1,2}(?:er)?\s+\w+|lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|fois\s+par\s+semaine)\b",
    re.IGNORECASE,
)
_TIME_RANGE_RE = re.compile(
    r"(?:de|entre)\s*(?P<h1>\d{1,2})\s*(?:(?:h|:|heures?)\s*(?P<m1>\d{1,2})?)?\s*"
    r"(?:à|a|et|-)\s*(?P<h2>\d{1,2})\s*(?:(?:h|:|heures?)\s*(?P<m2>\d{1,2})?)?",
    re.IGNORECASE,
)
_MIXED_LAWN_RE = re.compile(
    r"^arrosage\s+des\s+pelouses\s+interdit\s*[.!]?\s*"
    r"interdiction\s+horaire\s+de\s+(?P<h1>\d{1,2})\s*h\s*(?P<m1>\d{1,2})?\s*"
    r"(?:à|a|-)\s*(?P<h2>\d{1,2})\s*h\s*(?P<m2>\d{1,2})?\s*"
    r"pour\s+les\s+autres\s+usages\s*[.!]?$",
    re.IGNORECASE,
)
_MIXED_PELOUSE_MASSIF_RE = re.compile(
    r"^pelouse\s*:\s*interdit\s*[.;]?\s*"
    r"massif(?:s)?\s+fleuri(?:s)?\s*:\s*interdit\s+"
    r"(?:de|entre)\s*(?P<h1>\d{1,2})\s*h\s*(?P<m1>\d{1,2})?\s*"
    r"(?:à|a|et|-)\s*(?P<h2>\d{1,2})\s*h\s*(?P<m2>\d{1,2})?\s*[.!]?$",
    re.IGNORECASE,
)


def _clean(value: str) -> str:
    return _SPACE_RE.sub(" ", (value or "").replace("\xa0", " ")).strip()


def _fold(value: str) -> str:
    value = _clean(value).casefold().replace("’", "'")
    return _TRAILING_PUNCT_RE.sub("", value)


def _window(match: re.Match[str]) -> TimeWindow | None:
    h1 = int(match.group("h1")); h2 = int(match.group("h2"))
    m1 = int(match.groupdict().get("m1") or 0); m2 = int(match.groupdict().get("m2") or 0)
    if not (0 <= h1 <= 23 and 0 <= h2 <= 23 and 0 <= m1 <= 59 and 0 <= m2 <= 59):
        return None
    return TimeWindow(time(h1, m1), time(h2, m2))


def _contains_conditional_marker(text: str) -> bool:
    padded = f" {text} "
    return any(marker in padded for marker in _CONDITIONAL_MARKERS) or bool(_DATE_OR_DAY_RE.search(text))


def _looks_like_simple_time_ban(text: str) -> tuple[TimeWindow, ...] | None:
    if _contains_conditional_marker(text):
        return None
    matches = list(_TIME_RANGE_RE.finditer(text))
    if len(matches) != 1 or not _BAN_TOKEN_RE.search(text):
        return None
    unsafe_terms = (
        "réduction", "reduction", "registre", "volume", "prélèvement hebdomadaire",
        "prelevement hebdomadaire", "détail", "detail", "arrêté", "arrete",
        "strict minimum", "consommation", "retenue", "milieu naturel", "eau potable",
    )
    if any(term in text for term in unsafe_terms):
        return None
    window = _window(matches[0])
    return (window,) if window is not None else None


def _looks_like_unconditional_total_ban(text: str) -> bool:
    if not _BAN_TOKEN_RE.search(text):
        return False
    if _TIME_TOKEN_RE.search(text) or _contains_conditional_marker(text):
        return False
    if any(marker in text for marker in (
        "voir détails", "voir detail", "consulter", "plus d'information", "plus d’information",
        "à titre privé", "a titre prive", "à domicile", "a domicile", "en circuit ouvert",
        "sur les territoires", "sur décision", "sur decision", "peut être", "peuvent être",
    )):
        return False
    if text in {_fold(item) for item in _TOTAL_BAN_EXACT}:
        return True
    if len(text) <= 180 and re.fullmatch(
        r"(?:l[' ]|le |la |les |toute? |remplissage |vidange |alimentation )?.*\b(?:est |sont )?interdit(?:e|es|s)?",
        text, re.IGNORECASE,
    ):
        return True
    if len(text) <= 140 and re.fullmatch(
        r"interdiction(?: totale)?(?: de| des| du| de la| d').+", text, re.IGNORECASE
    ):
        return True
    return False


def interpret_usage(description: str) -> UsageInterpretation:
    source_text = description or ""
    text = _fold(source_text)
    if not text:
        return UsageInterpretation(InterpretationKind.UNKNOWN, None, (), source_text)
    if text in {_fold(item) for item in _NO_RESTRICTION_EXACT}:
        rule = InterpretedRule("Usage", InterpretationKind.NO_RESTRICTION, False)
        return UsageInterpretation(InterpretationKind.NO_RESTRICTION, False, (rule,), source_text)
    if text.startswith(_ADVISORY_PREFIXES):
        rule = InterpretedRule("Usage", InterpretationKind.ADVISORY, False)
        return UsageInterpretation(InterpretationKind.ADVISORY, False, (rule,), source_text)
    mixed = _MIXED_LAWN_RE.fullmatch(text)
    if mixed:
        window = _window(mixed)
        assert window is not None
        rules = (
            InterpretedRule("Arrosage des pelouses", InterpretationKind.TOTAL_BAN, True),
            InterpretedRule("Autres usages", InterpretationKind.TIME_BAN, True, (window,)),
        )
        return UsageInterpretation(InterpretationKind.MIXED, True, rules, source_text)
    mixed = _MIXED_PELOUSE_MASSIF_RE.fullmatch(text)
    if mixed:
        window = _window(mixed)
        assert window is not None
        rules = (
            InterpretedRule("Pelouse", InterpretationKind.TOTAL_BAN, True),
            InterpretedRule("Massifs fleuris", InterpretationKind.TIME_BAN, True, (window,)),
        )
        return UsageInterpretation(InterpretationKind.MIXED, True, rules, source_text)
    windows = _looks_like_simple_time_ban(text)
    if windows:
        rule = InterpretedRule("Usage", InterpretationKind.TIME_BAN, True, windows)
        return UsageInterpretation(InterpretationKind.TIME_BAN, True, (rule,), source_text)
    if _looks_like_unconditional_total_ban(text):
        rule = InterpretedRule("Usage", InterpretationKind.TOTAL_BAN, True)
        return UsageInterpretation(InterpretationKind.TOTAL_BAN, True, (rule,), source_text)
    if _BAN_TOKEN_RE.search(text):
        rule = InterpretedRule("Usage", InterpretationKind.CONDITIONAL, True)
        return UsageInterpretation(InterpretationKind.CONDITIONAL, True, (rule,), source_text)
    return UsageInterpretation(InterpretationKind.UNKNOWN, None, (), source_text)
