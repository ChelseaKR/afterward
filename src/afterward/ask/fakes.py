"""Scripted stand-ins for the model, for tests and for the eval harness's dry run.

Nothing here is intelligent and nothing here is meant to be. :func:`echo_narrator` reads the
evidence pack text back as claims -- one per record, citing it, declaring the first figure it
finds and naming every NOT REPORTED field as not reported -- so the whole pipeline can be
exercised, and the verifier shown to accept a faithful narration, without a model. A run
that uses it is labelled ``provider: fake`` and is never a measurement of anything.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from afterward.ask.provider import FakeProvider

RECORD_LINE = re.compile(r"^\[(?P<id>P:[^\]]+|O:[^\]]+|PEERS)\] (?P<kind>\w+): (?P<name>.*)$")
FIELD_LINE = re.compile(r"^  (?P<field>[\w.]+): (?P<value>.*)$")
NUMBER = re.compile(r"^-?\$?(?P<number>[\d,]+(?:\.\d+)?)(?:%|\s*\(|\s*\[|\s*--|$)")
"""A rendered figure, and not the first half of a period like ``2024-2034``."""


def structured_query(**overrides: Any) -> dict[str, Any]:
    """A complete, schema-shaped query dict with every field present."""
    base: dict[str, Any] = {
        "language": "en",
        "intent": "find_programs",
        "occupation_terms": [],
        "occupation_terms_english": [],
        "current_occupation_terms": [],
        "current_occupation_terms_english": [],
        "region_terms": [],
        "projection": "any",
        "min_annual_wage": None,
        "max_cost": None,
        "max_weeks": None,
        "format": "any",
        "requires_reported_outcomes": False,
        "measures_of_interest": [],
        "clarifications_needed": [],
        "out_of_scope": None,
    }
    base.update(overrides)
    return base


def echo_narrator(user: str) -> dict[str, Any]:
    """Claims read straight off the rendered pack. Faithful by construction."""
    claims: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in user.splitlines():
        header = RECORD_LINE.match(line)
        if header:
            current = {"id": header["id"], "name": header["name"], "fields": []}
            claims.append(_claim_for(current))
            continue
        field_line = FIELD_LINE.match(line)
        if field_line and current is not None:
            _absorb(claims[-1], current, field_line["field"], field_line["value"])
    claims.append(
        {
            "text": "Ask the provider or an America's Job Center before deciding.",
            "kind": "guidance",
            "cites": [],
            "numbers": [],
        }
    )
    return {"claims": claims, "follow_up_questions": []}


def _claim_for(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "text": f"{record['name']}.",
        "kind": "data",
        "cites": [record["id"]],
        "numbers": [],
    }


def _absorb(claim: dict[str, Any], record: dict[str, Any], field: str, value: str) -> None:
    if value.startswith("NOT REPORTED"):
        claim["text"] += f" {field} is not reported."
        return
    if claim["numbers"]:
        return
    match = NUMBER.match(value)
    if not match:
        return
    number = float(match["number"].replace(",", ""))
    period = ""
    if "[one quarter]" in value:
        period = " in one quarter"
    elif "[per year]" in value:
        period = " a year"
    claim["text"] += f" {field} is {match['number']}{period}."
    claim["numbers"].append({"record": record["id"], "field": field, "value": number})


def scripted(structure: dict[str, Any] | Callable[[str], dict[str, Any]]) -> FakeProvider:
    """A fake that answers ``structure`` with the given query and ``narrate`` by echoing."""

    def script(route: str, user: str) -> dict[str, Any]:
        if route == "structure":
            return structure(user) if callable(structure) else dict(structure)
        if route == "narrate":
            return echo_narrator(user)
        raise AssertionError(f"unscripted route {route}")

    return FakeProvider(script)
