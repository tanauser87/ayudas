from __future__ import annotations

import html
import re
import unicodedata
from datetime import date, datetime
from urllib.parse import urljoin

from .models import NOT_FOUND, Opportunity


MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

DATE_RE = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
    r"\d{1,2}\s+de\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|octubre|noviembre|diciembre)\s+de\s+\d{4})\b",
    re.I,
)


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", value)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", clean_text(value))
    normalized = "".join(character for character in normalized if not unicodedata.combining(character))
    return normalized.lower()


def parse_date(value: str) -> date | None:
    value = clean_text(value)
    iso_match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", value)
    if iso_match:
        try:
            return date.fromisoformat(iso_match.group(0))
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    match = re.fullmatch(
        r"(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(\d{4})",
        value,
        re.I,
    )
    if match:
        month = MONTHS.get(normalize_text(match.group(2)))
        if month:
            return date(int(match.group(3)), month, int(match.group(1)))
    return None


def context_after(text: str, terms: list[str], width: int = 350) -> str:
    cleaned = clean_text(text)
    normalized = normalize_text(cleaned)
    for term in terms:
        index = normalized.find(normalize_text(term))
        if index >= 0:
            return cleaned[index : index + width].strip(" .,:;")
    return NOT_FOUND


def date_near_terms(text: str, terms: list[str]) -> str:
    context = context_after(text, terms, width=250)
    if context == NOT_FOUND:
        return NOT_FOUND
    match = DATE_RE.search(context)
    if not match:
        return NOT_FOUND
    parsed = parse_date(match.group(0))
    return parsed.isoformat() if parsed else match.group(0)


def extract_status(open_date: str, close_date: str, text: str, today: date) -> str:
    normalized = normalize_text(text)
    parsed_open = parse_date(open_date)
    parsed_close = parse_date(close_date)
    if parsed_open and parsed_open > today:
        return "Próxima"
    if parsed_close:
        if parsed_close >= today and (not parsed_open or parsed_open <= today):
            return "Abierta"
        if parsed_close < today:
            return "Cerrada recurrente" if any(
                term in normalized for term in ["anual", "cada año", "edicion", "edición", "convocatorias anteriores"]
            ) else "Cerrada"
    if any(term in normalized for term in ["convocatoria abierta", "plazo abierto", "presentación de solicitudes"]):
        return "Abierta"
    if any(term in normalized for term in ["convocatoria cerrada", "plazo cerrado", "estado cerrada"]):
        return "Cerrada recurrente" if any(
            term in normalized for term in ["anual", "cada año", "convocatorias anteriores"]
        ) else "Cerrada"
    return "Desconocida"


def extract_money(text: str, nearby_terms: list[str]) -> str:
    context = context_after(text, nearby_terms, width=220)
    if context == NOT_FOUND:
        return NOT_FOUND
    match = re.search(
        r"(?:(?:€|euros?)\s*)?(\d[\d.\s]*(?:,\d{1,2})?)\s*(?:€|euros?)",
        context,
        re.I,
    )
    return clean_text(match.group(0)) if match else NOT_FOUND


def extract_percentage(text: str, nearby_terms: list[str]) -> str:
    context = context_after(text, nearby_terms, width=220)
    if context == NOT_FOUND:
        return NOT_FOUND
    match = re.search(r"\b\d{1,3}(?:[.,]\d+)?\s*%", context)
    return match.group(0) if match else NOT_FOUND


def extract_link(html_text: str, base_url: str, labels: list[str]) -> str:
    for match in re.finditer(r'(?is)<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html_text):
        label = normalize_text(match.group(2))
        if any(normalize_text(term) in label for term in labels):
            return urljoin(base_url, html.unescape(match.group(1)))
    return NOT_FOUND


def enrich_opportunity(opportunity: Opportunity, html_text: str, today: date) -> Opportunity:
    text = clean_text(html_text)
    opportunity.raw_text = text[:30_000]
    opportunity.open_date = date_near_terms(
        text,
        ["fecha de apertura", "plazo de presentación", "desde el", "se iniciará"],
    )
    opportunity.close_date = date_near_terms(
        text,
        ["fecha de cierre", "hasta el", "finalizará", "fecha límite", "fin de plazo"],
    )
    opportunity.status = extract_status(opportunity.open_date, opportunity.close_date, text, today)
    opportunity.total_budget = extract_money(
        text,
        ["presupuesto total", "dotación presupuestaria", "presupuesto de la convocatoria"],
    )
    opportunity.max_amount = extract_money(
        text,
        ["importe máximo", "cuantía máxima", "por proyecto", "por solicitud"],
    )
    opportunity.financing_rate = extract_percentage(
        text,
        ["porcentaje financiable", "financiación", "coste subvencionable"],
    )
    opportunity.cofinancing = context_after(text, ["cofinanciación", "aportación propia"], 220)
    opportunity.advance_payment = context_after(text, ["anticipo", "pago anticipado"], 220)
    opportunity.beneficiaries = context_after(
        text,
        ["beneficiarios", "beneficiarias", "podrán solicitar", "entidades solicitantes"],
        550,
    )
    opportunity.seniority_requirements = context_after(text, ["antigüedad", "constituidas desde"], 260)
    opportunity.staff_requirements = context_after(text, ["personal contratado", "contratación de personal"], 260)
    opportunity.partners_required = context_after(text, ["socio", "entidad colaboradora"], 260)
    opportunity.consortium_required = context_after(text, ["consorcio", "consortium"], 260)
    opportunity.eligible_expenses = context_after(
        text,
        ["gastos subvencionables", "costes elegibles", "gastos elegibles"],
        500,
    )
    opportunity.duration = context_after(text, ["duración", "periodo de ejecución"], 260)
    opportunity.bases_url = extract_link(html_text, opportunity.official_url, ["bases", "convocatoria"])
    opportunity.application_url = extract_link(
        html_text,
        opportunity.official_url,
        ["solicitud", "sede electrónica", "tramitar", "gestión"],
    )
    return opportunity
