from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import urllib.parse
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .models import NOT_FOUND, Opportunity


TRACKED_FIELDS = {
    "close_date": "cambio de plazo",
    "open_date": "cambio de apertura",
    "total_budget": "cambio de presupuesto total",
    "max_amount": "cambio de importe máximo",
    "status": "cambio de estado",
}


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(character for character in normalized if not unicodedata.combining(character))
    normalized = re.sub(r"\b(?:19|20)\d{2}\b", " ", normalized.lower())
    return re.sub(r"[^a-z0-9]+", " ", normalized).strip()


def canonical_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url or "")
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(key, value) for key, value in query if not key.lower().startswith(("utm_", "fbclid"))]
    path = re.sub(r"/+$", "", parsed.path) or "/"
    return urllib.parse.urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), path, urllib.parse.urlencode(query), "")
    )


def stable_id(opportunity: Opportunity) -> str:
    if opportunity.id:
        return opportunity.id
    basis = canonical_url(opportunity.official_url) or (
        f"{opportunity.source}|{normalize_text(opportunity.title)}|{opportunity.published_date}"
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def information_score(opportunity: Opportunity) -> int:
    data = opportunity.to_dict()
    return sum(
        value not in ("", NOT_FOUND, [], {}, None)
        for key, value in data.items()
        if key not in {"raw_text", "changes"}
    )


def deduplicate(opportunities: list[Opportunity]) -> list[Opportunity]:
    unique: dict[str, Opportunity] = {}
    url_index: dict[str, str] = {}
    for opportunity in opportunities:
        opportunity.id = stable_id(opportunity)
        url = canonical_url(opportunity.official_url)
        existing_id = url_index.get(url) if url else None
        key = existing_id or opportunity.id
        existing = unique.get(key)
        if existing is None or information_score(opportunity) > information_score(existing):
            if existing_id and opportunity.id != existing_id:
                opportunity.id = existing_id
            unique[key] = opportunity
        if url:
            url_index[url] = key
    return list(unique.values())


def empty_history() -> dict[str, Any]:
    return {"version": 1, "opportunities": {}, "events": []}


def load_history(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_history()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_history()
    if not isinstance(payload, dict):
        return empty_history()
    payload.setdefault("opportunities", {})
    payload.setdefault("events", [])
    return payload


def recurring_fingerprint(title: str) -> str:
    normalized = normalize_text(title)
    return re.sub(
        r"\b(?:convocatoria|extracto|resolucion|orden|ayudas?|subvenciones?|edicion)\b",
        " ",
        normalized,
    ).strip()


def _published_date(opportunity: Opportunity) -> date | None:
    match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", opportunity.published_date)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(0))
    except ValueError:
        return None


def apply_recurrence(opportunities: list[Opportunity], history: dict[str, Any]) -> None:
    dates_by_fingerprint: dict[str, list[date]] = {}
    for record in history.get("opportunities", {}).values():
        previous = Opportunity.from_dict(record)
        published = _published_date(previous)
        if published:
            dates_by_fingerprint.setdefault(recurring_fingerprint(previous.title), []).append(published)

    for opportunity in opportunities:
        fingerprint = recurring_fingerprint(opportunity.title)
        if len(fingerprint) < 8:
            continue
        dates = dates_by_fingerprint.get(fingerprint, [])
        current_date = _published_date(opportunity)
        if current_date and current_date not in dates:
            dates.append(current_date)
        years = {item.year for item in dates}
        if len(years) < 2:
            continue
        opportunity.recurrent = True
        latest = max(dates)
        estimated = latest + timedelta(days=365)
        opportunity.estimated_next_call = f"Estimación histórica: {estimated.isoformat()}"
        if opportunity.status == "Cerrada":
            opportunity.status = "Cerrada recurrente"


def update_history(
    opportunities: list[Opportunity],
    history: dict[str, Any],
    checked_at: str,
) -> dict[str, Any]:
    updated = deepcopy(history)
    records = updated.setdefault("opportunities", {})
    events = updated.setdefault("events", [])
    for opportunity in opportunities:
        opportunity.id = stable_id(opportunity)
        previous_data = records.get(opportunity.id)
        opportunity.is_new = previous_data is None
        opportunity.first_seen = checked_at
        opportunity.last_seen = checked_at
        if previous_data:
            previous = Opportunity.from_dict(previous_data)
            opportunity.first_seen = previous.first_seen or previous.checked_at or checked_at
            for field, label in TRACKED_FIELDS.items():
                old_value = getattr(previous, field)
                new_value = getattr(opportunity, field)
                if old_value != new_value and new_value not in ("", NOT_FOUND):
                    change = f"{label}: {old_value} -> {new_value}"
                    opportunity.changes.append(change)
                    events.append(
                        {
                            "opportunity_id": opportunity.id,
                            "detected_at": checked_at,
                            "change": change,
                        }
                    )
            if previous.status == "Cerrada" and opportunity.status == "Abierta":
                opportunity.changes.append("reapertura detectada")
        records[opportunity.id] = opportunity.to_dict()
    updated["updated_at"] = checked_at
    updated["events"] = events[-2_000:]
    return updated


def save_history(path: Path, history: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_current_data(path: Path, opportunities: list[Opportunity]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [opportunity.to_dict() for opportunity in opportunities]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
