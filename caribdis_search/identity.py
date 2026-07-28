from __future__ import annotations

import re
from typing import Any

from .extractors import clean_text
from .models import NOT_FOUND, Opportunity


def extract_bdns_number(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, (int, float)):
            digits = str(int(value))
            if len(digits) >= 3:
                return digits
        text = clean_text(str(value))
        if text.isdigit() and len(text) >= 3:
            return text
        match = re.search(
            r"\b(?:c[oó]digo\s+)?BDNS(?:\s*\(Identif\.?\))?"
            r"\s*(?:n[úu]m(?:ero)?\.?|[:#-])?\s*(\d{3,12})\b",
            text,
            re.I,
        )
        if match:
            return match.group(1)
    return NOT_FOUND


def extract_official_identifiers(*values: Any) -> list[str]:
    identifiers: list[str] = []
    for value in values:
        text = clean_text(str(value or ""))
        for match in re.findall(r"\bBOE-[A-Z]-\d{4}-\d+\b", text, re.I):
            normalized = match.upper()
            if normalized not in identifiers:
                identifiers.append(normalized)
        for match in re.findall(r"\bBOJA-\d{4}-\d+(?:-\d+)?\b", text, re.I):
            normalized = match.upper()
            if normalized not in identifiers:
                identifiers.append(normalized)
        boja_url = re.search(r"/boja/(\d{4})/(\d+)/(\d+)\.html", text, re.I)
        if boja_url:
            identifier = f"BOJA-{boja_url.group(1)}-{boja_url.group(2)}-{boja_url.group(3)}"
            if identifier not in identifiers:
                identifiers.append(identifier)
    return identifiers


def populate_official_identity(opportunity: Opportunity) -> Opportunity:
    values = [
        opportunity.bdns_number,
        opportunity.title,
        opportunity.summary,
        opportunity.raw_text,
        opportunity.official_url,
        opportunity.bases_url,
        *opportunity.official_links,
        *opportunity.official_identifiers,
    ]
    bdns_number = extract_bdns_number(*values)
    if bdns_number != NOT_FOUND:
        opportunity.bdns_number = bdns_number
    opportunity.official_identifiers = list(
        dict.fromkeys(
            opportunity.official_identifiers + extract_official_identifiers(*values)
        )
    )
    if opportunity.source and opportunity.source != NOT_FOUND:
        opportunity.source_references = list(
            dict.fromkeys(opportunity.source_references + [opportunity.source])
        )
    return opportunity
