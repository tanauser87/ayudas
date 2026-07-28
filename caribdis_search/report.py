from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

from .models import NOT_FOUND, Incident, Opportunity, RunResult


STATUS_ORDER = {
    "abierta": 0,
    "proxima": 1,
    "cerrada recurrente": 2,
    "desconocida": 3,
    "cerrada": 4,
}

PRIORITY_ORDER = {
    "muy alta": 0,
    "alta": 1,
    "media": 2,
    "baja": 3,
    "descartar": 4,
}


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(character for character in normalized if not unicodedata.combining(character))
    return re.sub(r"\s+", " ", normalized).strip().lower()


def parse_iso_date(value: str) -> date | None:
    match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", value or "")
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def numeric_amount(value: str) -> float:
    matches = re.findall(r"\d[\d.,]*", value or "")
    if not matches:
        return 0
    cleaned = matches[0].replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return 0


def administrative_difficulty(opportunity: Opportunity) -> int:
    difficulty = len(opportunity.risks)
    if opportunity.consortium_required != NOT_FOUND:
        difficulty += 3
    if opportunity.cofinancing != NOT_FOUND:
        difficulty += 2
    if opportunity.participation != "Solicitud directa":
        difficulty += 1
    return difficulty


def ranking_key(opportunity: Opportunity, today: date | None = None) -> tuple[object, ...]:
    today = today or date.today()
    normalized_status = normalize_text(opportunity.status)
    normalized_priority = normalize_text(opportunity.priority)
    status = STATUS_ORDER.get(normalized_status, 3)
    close_date = parse_iso_date(opportunity.close_date)
    days_to_close = (close_date - today).days if close_date else 999_999
    direct_order = 0 if opportunity.participation == "Solicitud directa" else 1
    partner = opportunity.participation in {
        "Socia de ayuntamiento",
        "Socia de universidad o centro científico",
        "Socia de consorcio europeo",
        "Solo con socio",
    }
    if normalized_status == "abierta" and normalized_priority in {"muy alta", "alta"} and not partner:
        operational_bucket = 0
    elif normalized_status == "abierta" and normalized_priority == "media" and not partner:
        operational_bucket = 1
    elif normalized_status in {"proxima", "cerrada recurrente"} and not partner:
        operational_bucket = 2
    elif partner:
        operational_bucket = 3
    elif normalized_status == "abierta":
        operational_bucket = 4
    else:
        operational_bucket = 5
    amount = max(numeric_amount(opportunity.max_amount), numeric_amount(opportunity.total_budget))
    return (
        operational_bucket,
        PRIORITY_ORDER.get(normalized_priority, 4),
        -opportunity.caribdis_score,
        status,
        days_to_close,
        direct_order,
        -amount,
        administrative_difficulty(opportunity),
        opportunity.title.lower(),
        opportunity.official_url,
    )


def ranked_opportunities(
    opportunities: list[Opportunity],
    today: date | None = None,
) -> list[Opportunity]:
    return sorted(opportunities, key=lambda item: ranking_key(item, today=today))


def markdown_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().replace("|", r"\|")


def value_or_not_found(value: str) -> str:
    return value if value and value.strip() else NOT_FOUND


def render_compact_table(opportunities: list[Opportunity], limit: int | None = None) -> list[str]:
    selected = opportunities[:limit] if limit is not None else opportunities
    if not selected:
        return ["No se han localizado oportunidades en esta sección.", ""]
    lines = [
        "| Puntuación | Prioridad | Estado | Participación | Oportunidad | Cierre |",
        "|---:|---|---|---|---|---|",
    ]
    for item in selected:
        title = markdown_text(item.title)
        link = f"[{title}]({item.official_url})" if item.official_url else title
        lines.append(
            f"| {item.caribdis_score} | {item.priority} | {item.status} | "
            f"{item.participation} | {link} | {value_or_not_found(item.close_date)} |"
        )
    lines.append("")
    return lines


def render_discarded_table(opportunities: list[Opportunity]) -> list[str]:
    if not opportunities:
        return ["No se han localizado ayudas descartadas.", ""]
    lines = [
        "| Oportunidad | Organismo | Motivo del descarte |",
        "|---|---|---|",
    ]
    for item in opportunities:
        title = markdown_text(item.title)
        link = f"[{title}]({item.official_url})" if item.official_url else title
        reason = "; ".join(item.risks) or item.score_reason
        lines.append(f"| {link} | {markdown_text(item.organization)} | {markdown_text(reason)} |")
    lines.append("")
    return lines


def render_source_coverage(run: RunResult) -> list[str]:
    labels = {
        "historical": "Histórica",
        "api": "API",
        "rss": "RSS",
        "current": "Actual",
        "landing": "Página de portada",
    }
    if not run.source_statuses:
        return ["No hay fuentes estables seleccionadas en esta ejecución.", ""]
    lines = [
        "| Fuente | Cobertura | Alcance real |",
        "|---|---|---|",
    ]
    for status in run.source_statuses:
        lines.append(
            f"| {markdown_text(status.source_name)} | "
            f"{labels.get(status.coverage_type, status.coverage_type)} | "
            f"{markdown_text(status.coverage_note)} |"
        )
    lines.append("")
    return lines


def render_pending_sources(run: RunResult) -> list[str]:
    if not run.pending_sources:
        return ["No hay fuentes seleccionadas pendientes de adaptación.", ""]
    lines = [
        "Estas fuentes están desactivadas por defecto y no generan oportunidades rankeadas.",
        "",
        "| Fuente | Motivo |",
        "|---|---|",
    ]
    for status in run.pending_sources:
        reason = status.adjustment_reason or "El listado requiere un adaptador específico verificable."
        lines.append(f"| {markdown_text(status.source_name)} | {markdown_text(reason)} |")
    lines.append("")
    return lines


def render_detailed_opportunity(item: Opportunity, position: int) -> list[str]:
    risks = "; ".join(item.risks) if item.risks else "No se han identificado riesgos explícitos."
    warnings = "; ".join(item.warnings) if item.warnings else "Ninguna advertencia adicional."
    keywords = ", ".join(item.caribdis_keywords) if item.caribdis_keywords else "Ninguna."
    official_identifiers = ", ".join(item.official_identifiers) or NOT_FOUND
    official_links = ", ".join(item.official_links) or NOT_FOUND
    european_funds = ", ".join(item.european_funds) or NOT_FOUND
    aid_instruments = ", ".join(item.aid_instruments) or NOT_FOUND
    administrative_events = ", ".join(item.administrative_events) or NOT_FOUND
    return [
        f"### {position}. {item.title} — {item.caribdis_score}/100 — PRIORIDAD {item.priority.upper()}",
        "",
        f"- Estado: {item.status}",
        f"- Apertura: {value_or_not_found(item.open_date)}",
        f"- Plazo: {value_or_not_found(item.close_date)}",
        f"- Organismo: {item.organization}",
        f"- Tipo de organismo: {item.organization_type}",
        f"- Fuente: {item.source}",
        f"- Cobertura de la fuente: {item.coverage_type} — {item.coverage_note or NOT_FOUND}",
        f"- Metadatos verificados: {'Sí' if item.metadata_verified else 'No consta revisión completa'}",
        f"- Número BDNS: {item.bdns_number}",
        f"- Identificadores BOE/BOJA: {official_identifiers}",
        f"- Fecha de registro: {item.registered_date}",
        f"- Tipo de registro: {item.record_type}",
        f"- Solicitabilidad: {item.solicitability}",
        f"- Territorio: {item.territory}",
        f"- Nivel administrativo/comunidad autónoma: {item.administrative_level} / {item.autonomous_community}",
        f"- Provincia/municipio: {item.province} / {item.municipality}",
        f"- Presupuesto de la convocatoria: {item.total_budget}",
        f"- Importe máximo por proyecto: {item.max_amount}",
        f"- Financiación: {item.financing_rate}",
        f"- Cofinanciación: {item.cofinancing}",
        f"- Anticipo: {item.advance_payment}",
        f"- ¿Puede pedirla CARIBDIS directamente?: {item.participation}",
        f"- Beneficiarios: {item.beneficiaries}",
        f"- Requisitos: {item.requirements}",
        f"- Antigüedad/experiencia: {item.seniority_requirements} / {item.experience_requirements}",
        f"- Necesidad de socios/consorcio: {item.partners_required} / {item.consortium_required}",
        f"- Necesidad de aval: {item.guarantee_requirements}",
        f"- Gastos subvencionables: {item.eligible_expenses}",
        f"- Duración: {item.duration}",
        f"- Fondos europeos: {european_funds}",
        f"- Instrumentos de ayuda: {aid_instruments}",
        f"- Eventos administrativos: {administrative_events}",
        f"- Temática principal: {item.main_theme}",
        f"- Palabras clave: {keywords}",
        f"- Motivo de la puntuación: {item.score_reason}",
        f"- Requisitos o riesgos: {risks}",
        f"- Proyecto recomendado: {item.recommended_project}",
        f"- Advertencias: {warnings}",
        f"- Enlace oficial: {item.official_url or NOT_FOUND}",
        f"- Otros enlaces oficiales: {official_links}",
        f"- Bases: {item.bases_url}",
        f"- Sede electrónica: {item.application_url}",
        "",
    ]


def _contains(value: str, terms: list[str]) -> bool:
    normalized = normalize_text(value)
    return any(normalize_text(term) in normalized for term in terms)


def _filter(
    opportunities: list[Opportunity],
    predicate: Callable[[Opportunity], bool],
) -> list[Opportunity]:
    return [item for item in opportunities if predicate(item)]


def _months_from_now(target: date, today: date) -> int:
    return (target.year - today.year) * 12 + target.month - today.month


def render_calendar(opportunities: list[Opportunity], today: date) -> list[str]:
    buckets: dict[str, list[Opportunity]] = {
        "Próximos 3 meses": [],
        "Próximos 6 meses": [],
        "Próximos 12 meses": [],
    }
    for item in opportunities:
        target = parse_iso_date(item.close_date) or parse_iso_date(item.estimated_next_call)
        if not target or target < today:
            continue
        months = _months_from_now(target, today)
        if months <= 3:
            buckets["Próximos 3 meses"].append(item)
        elif months <= 6:
            buckets["Próximos 6 meses"].append(item)
        elif months <= 12:
            buckets["Próximos 12 meses"].append(item)

    lines: list[str] = []
    for heading, items in buckets.items():
        lines.extend([f"### {heading}", ""])
        lines.extend(render_compact_table(items))
    if not any(buckets.values()):
        lines.append(
            "No hay fechas oficiales o estimaciones históricas suficientes para construir el calendario."
        )
        lines.append("")
    return lines


def render_incidents(incidents: list[Incident]) -> list[str]:
    if not incidents:
        return ["No se registraron incidencias de consulta.", ""]
    return [
        *(f"- {incident.source_name}: {incident.message}" for incident in incidents),
        "",
    ]


def render_report(
    run: RunResult,
    start_date: date,
    end_date: date,
    today: date | None = None,
) -> str:
    today = today or date.today()
    ranked = ranked_opportunities(run.opportunities, today=today)
    eligible = _filter(ranked, lambda item: item.priority != "Descartar")
    top_eligible = _filter(
        eligible,
        lambda item: item.priority != "Baja" or item.thematic_minimum_met,
    )
    open_items = _filter(top_eligible, lambda item: normalize_text(item.status) == "abierta")
    upcoming = _filter(top_eligible, lambda item: normalize_text(item.status) == "proxima")
    recurrent = _filter(top_eligible, lambda item: normalize_text(item.status) == "cerrada recurrente")
    discarded = _filter(ranked, lambda item: item.priority == "Descartar")

    lines = [
        "# INFORME ÚNICO DE AYUDAS CARIBDIS",
        "",
        "## 1. Fecha y periodo revisado",
        "",
        f"- Ejecución: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- Periodo revisado: {start_date.isoformat()} a {end_date.isoformat()}",
        f"- Fuentes comprobadas: {len(run.sources_checked)}",
        f"- Fuentes consultadas con éxito: {len(run.sources_succeeded)}",
        "",
        "## 2. Resumen ejecutivo",
        "",
        f"- Oportunidades únicas: {len(ranked)}",
        f"- Abiertas: {len(open_items)}",
        f"- Próximas: {len(upcoming)}",
        f"- Cerradas recurrentes: {len(recurrent)}",
        f"- Solicitud directa: {sum(item.participation == 'Solicitud directa' for item in ranked)}",
        f"- Prioridad muy alta o alta: {sum(item.priority in {'Muy alta', 'Alta'} for item in ranked)}",
        f"- Incidencias: {len(run.incidents)}",
        "",
        "### Cobertura real por fuente",
        "",
        *render_source_coverage(run),
        "### Fuentes con incidencias",
        "",
        *render_incidents(run.incidents),
        "### Fuentes pendientes de adaptación",
        "",
        *render_pending_sources(run),
        "## 3. Top 10 ayudas abiertas para solicitar ahora",
        "",
        *render_compact_table(open_items, 10),
        "## 4. Top 10 ayudas próximas o esperadas",
        "",
        *render_compact_table(upcoming, 10),
        "## 5. Top 10 ayudas cerradas pero recurrentes",
        "",
        *render_compact_table(recurrent, 10),
    ]

    grouped_sections: list[tuple[str, list[Opportunity]]] = [
        (
            "6. Ayudas de la Unión Europea",
            _filter(eligible, lambda item: _contains(f"{item.source_group} {item.territory}", ["Europa", "Unión Europea"])),
        ),
        (
            "7. Ayudas estatales",
            _filter(eligible, lambda item: _contains(f"{item.source_group} {item.territory}", ["Estatal", "España", "BDNS"])),
        ),
        (
            "8. Ayudas de la Junta de Andalucía",
            _filter(eligible, lambda item: _contains(item.source_group, ["Junta de Andalucía", "BOJA"])),
        ),
        (
            "9. Ayudas de diputaciones andaluzas",
            _filter(eligible, lambda item: _contains(item.source_group, ["Diputación"])),
        ),
        (
            "10. Ayudas de ayuntamientos y entidades locales",
            _filter(eligible, lambda item: _contains(item.source_group, ["Ayuntamiento", "Entidad local", "Municipal"])),
        ),
        (
            "11. Ayudas GALP/GALPA/FEMPA",
            _filter(eligible, lambda item: _contains(f"{item.source_group} {item.title}", ["GALP", "GALPA", "FEMPA", "Pleamar"])),
        ),
        (
            "12. Ayudas de fundaciones privadas",
            _filter(
                eligible,
                lambda item: _contains(
                    f"{item.source_group} {item.organization_type}",
                    ["Fundaciones privadas", "Fundación privada", "RSC"],
                ),
            ),
        ),
        (
            "13. Ayudas que CARIBDIS puede solicitar directamente",
            _filter(eligible, lambda item: item.participation == "Solicitud directa"),
        ),
        (
            "14. Ayudas que requieren ayuntamiento",
            _filter(eligible, lambda item: item.participation == "Socia de ayuntamiento"),
        ),
        (
            "15. Ayudas que requieren universidad o centro científico",
            _filter(eligible, lambda item: item.participation == "Socia de universidad o centro científico"),
        ),
        (
            "16. Ayudas que requieren consorcio europeo",
            _filter(eligible, lambda item: item.participation == "Socia de consorcio europeo"),
        ),
        ("17. Ayudas descartadas y motivo", discarded),
    ]
    for heading, items in grouped_sections:
        renderer = render_discarded_table if heading.startswith("17.") else render_compact_table
        lines.extend([f"## {heading}", "", *renderer(items)])

    lines.extend(
        [
            "## 18. Calendario de próximos tres, seis y doce meses",
            "",
            *render_calendar(eligible, today),
            "## 19. Ranking general completo",
            "",
        ]
    )
    if eligible:
        for position, item in enumerate(eligible, 1):
            lines.extend(render_detailed_opportunity(item, position))
    else:
        lines.extend(["No se han localizado oportunidades verificables.", ""])

    immediate = [item for item in open_items if item.priority in {"Muy alta", "Alta"}][:5]
    lines.extend(["## 20. Recomendaciones de actuación inmediata", ""])
    if immediate:
        for item in immediate:
            lines.append(
                f"- Revisar hoy [{item.title}]({item.official_url}) y confirmar "
                f"beneficiarios, presupuesto y documentación antes de {item.close_date}."
            )
    else:
        lines.append(
            "- No hay ayudas abiertas de prioridad alta verificadas; revisar las próximas "
            "ediciones y resolver primero las incidencias de fuentes."
        )
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_report(
    path: Path,
    run: RunResult,
    start_date: date,
    end_date: date,
    today: date | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_report(run, start_date=start_date, end_date=end_date, today=today),
        encoding="utf-8",
    )
