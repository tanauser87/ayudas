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

CASHFLOW_ORDER = {
    "bajo": 0,
    "medio": 1,
    "alto": 2,
    "muy alto": 3,
    "no evaluado": 4,
}

PARTNER_PARTICIPATIONS = {
    "Socia de ayuntamiento",
    "Socia de universidad o centro científico",
    "Socia de consorcio europeo",
    "Solo con socio",
    "Participación mediante entidad socia",
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
    close_date = parse_iso_date(opportunity.close_date)
    days_to_close = (close_date - today).days if close_date else 999_999
    direct_order = 0 if opportunity.participation == "Solicitud directa" else 1
    new_entity_order = {
        True: 0,
        None: 1,
        False: 2,
    }[opportunity.suitable_for_new_entity]
    funding_text = normalize_text(
        f"{opportunity.funding_instrument} {opportunity.summary} {opportunity.raw_text}"
    )
    non_repayable_order = (
        0
        if any(
            term in funding_text
            for term in [
                "subvencion",
                "a fondo perdido",
                "donacion",
                "patrocinio",
                "convocatoria de fundacion",
            ]
        )
        else 1
    )
    advance_order = (
        0
        if opportunity.advance_percentage is not None
        and opportunity.advance_percentage > 0
        else 1
        if opportunity.advance_percentage is None
        else 2
    )
    thematic_fit = (
        opportunity.scoring.thematic_fit
        + opportunity.scoring.social_educational_fit
    )
    return (
        0 if normalized_status == "abierta" else 1,
        direct_order,
        PRIORITY_ORDER.get(normalized_priority, 4),
        new_entity_order,
        non_repayable_order,
        advance_order,
        CASHFLOW_ORDER.get(normalize_text(opportunity.cashflow_risk), 4),
        -thematic_fit,
        days_to_close,
        -opportunity.caribdis_score,
        STATUS_ORDER.get(normalized_status, 3),
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


def percentage_or_not_found(value: float | None) -> str:
    return f"{value:g} %" if value is not None else NOT_FOUND


def boolean_or_not_found(value: bool | None) -> str:
    if value is None:
        return NOT_FOUND
    return "Sí" if value else "No"


def amount_or_not_found(value: float | None) -> str:
    if value is None:
        return NOT_FOUND
    return f"{value:,.2f} €".replace(",", " ").replace(".", ",")


def payment_method(opportunity: Opportunity) -> str:
    if opportunity.reimbursement_only is True:
        return "Reembolso después de justificar"
    if opportunity.advance_percentage is not None and opportunity.advance_percentage > 0:
        return (
            f"Anticipo del {opportunity.advance_percentage:g} %; "
            f"liquidación restante: {NOT_FOUND}"
        )
    if opportunity.advance_payment != NOT_FOUND:
        return opportunity.advance_payment
    return NOT_FOUND


def render_compact_table(opportunities: list[Opportunity], limit: int | None = None) -> list[str]:
    selected = opportunities[:limit] if limit is not None else opportunities
    if not selected:
        return ["No se han localizado oportunidades en esta sección.", ""]
    lines = [
        "| Puntuación | Prioridad | Estado | Riesgo de tesorería | Participación | Oportunidad | Cierre |",
        "|---:|---|---|---|---|---|---|",
    ]
    for item in selected:
        title = markdown_text(item.title)
        link = f"[{title}]({item.official_url})" if item.official_url else title
        lines.append(
            f"| {item.caribdis_score} | {item.priority} | {item.status} | "
            f"{item.cashflow_risk} | "
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


def render_strategic_procedures(opportunities: list[Opportunity]) -> list[str]:
    if not opportunities:
        return ["No se han localizado trámites estratégicos verificables.", ""]
    lines: list[str] = []
    for position, item in enumerate(opportunities, 1):
        normalized = normalize_text(
            f"{item.title} {item.summary} {item.procedure_topic}"
        )
        if any(term in normalized for term in ["flora", "fauna", "biodiversidad"]):
            strength = (
                "Puede acreditar capacidad técnica y colaboración institucional "
                "en conservación de flora, fauna y biodiversidad."
            )
        elif any(term in normalized for term in ["voluntariado", "participacion"]):
            strength = (
                "Puede reforzar el reconocimiento y la capacidad operativa de "
                "CARIBDIS en programas de voluntariado."
            )
        else:
            strength = (
                "Puede aportar una acreditación o inscripción útil para futuras "
                "convocatorias y colaboraciones."
            )
        purpose = next(
            (
                value
                for value in [
                    item.summary,
                    item.procedure_kind,
                    item.procedure_topic,
                ]
                if value and value != NOT_FOUND
            ),
            NOT_FOUND,
        )
        documentation_parts = [
            value
            for value in [item.requirements, *item.forms]
            if value and value != NOT_FOUND
        ]
        documentation = "; ".join(documentation_parts) or NOT_FOUND
        recommendation = (
            "Revisar requisitos y preparar la tramitación mientras permanezca abierto."
            if normalize_text(item.status) == "abierta"
            else "Vigilar su reapertura y preparar con antelación la documentación."
        )
        lines.extend(
            [
                f"### {position}. {item.title}",
                "",
                f"- Código: {item.procedure_code}",
                f"- Organismo: {item.organization}",
                f"- Finalidad: {purpose}",
                f"- Por qué fortalece CARIBDIS: {strength}",
                f"- Documentación y requisitos: {documentation}",
                f"- Estado: {item.status}",
                f"- Enlace oficial: {item.official_url or NOT_FOUND}",
                f"- Recomendación: {recommendation}",
                "",
            ]
        )
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
    funding_purposes = ", ".join(item.funding_purposes) or NOT_FOUND
    administrative_events = ", ".join(item.administrative_events) or NOT_FOUND
    forms = "; ".join(item.forms) or NOT_FOUND
    legal_bases = "; ".join(item.legal_bases) or NOT_FOUND
    return [
        f"### {position}. {item.title} — {item.caribdis_score}/100 — PRIORIDAD {item.priority.upper()}",
        "",
        f"- Estado: {item.status}",
        f"- Apertura: {value_or_not_found(item.open_date)}",
        f"- Plazo: {value_or_not_found(item.close_date)}",
        f"- Organismo: {item.organization}",
        f"- Consejería: {item.counseling}",
        f"- Tipo de organismo: {item.organization_type}",
        f"- Fuente: {item.source}",
        f"- Cobertura de la fuente: {item.coverage_type} — {item.coverage_note or NOT_FOUND}",
        f"- Metadatos verificados: {'Sí' if item.metadata_verified else 'No consta revisión completa'}",
        f"- Número BDNS: {item.bdns_number}",
        f"- Código de procedimiento: {item.procedure_code}",
        f"- Identificadores oficiales: {official_identifiers}",
        f"- Fecha de registro: {item.registered_date}",
        f"- Tipo de registro: {item.record_type}",
        f"- Solicitabilidad: {item.solicitability}",
        f"- Familia/tema/actividad: {item.procedure_family} / {item.procedure_topic} / {item.procedure_activity}",
        f"- Tipo de procedimiento: {item.procedure_kind}",
        f"- Territorio: {item.territory}",
        f"- Nivel administrativo/comunidad autónoma: {item.administrative_level} / {item.autonomous_community}",
        f"- Provincia/municipio: {item.province} / {item.municipality}",
        f"- Presupuesto de la convocatoria: {item.total_budget}",
        f"- Importe máximo por proyecto: {item.max_amount}",
        f"- Financiación: {item.financing_rate}",
        f"- Cofinanciación: {item.cofinancing}",
        f"- Anticipo: {item.advance_payment}",
        f"- Instrumento financiero: {item.funding_instrument}",
        f"- Finalidad de la financiación: {funding_purposes}",
        f"- Porcentaje financiado: {percentage_or_not_found(item.funding_percentage)}",
        f"- Porcentaje de cofinanciación: {percentage_or_not_found(item.cofinancing_percentage)}",
        f"- Porcentaje de anticipo: {percentage_or_not_found(item.advance_percentage)}",
        f"- Aval para el anticipo: {boolean_or_not_found(item.advance_guarantee_required)}",
        f"- Pago solo tras justificar: {boolean_or_not_found(item.reimbursement_only)}",
        f"- Forma de pago: {payment_method(item)}",
        f"- Gastos de funcionamiento: {boolean_or_not_found(item.operating_costs_eligible)}",
        f"- Gastos de personal: {boolean_or_not_found(item.staff_costs_eligible)}",
        f"- Equipamiento: {boolean_or_not_found(item.equipment_eligible)}",
        f"- Alquiler de sede: {boolean_or_not_found(item.rent_eligible)}",
        f"- Seguros: {boolean_or_not_found(item.insurance_eligible)}",
        f"- Desplazamientos: {boolean_or_not_found(item.travel_eligible)}",
        f"- Antigüedad mínima estructurada: {item.minimum_seniority}",
        f"- Experiencia previa obligatoria: {boolean_or_not_found(item.previous_experience_required)}",
        f"- Presupuesto mínimo del proyecto: {amount_or_not_found(item.minimum_project_budget)}",
        f"- Auditoría obligatoria: {boolean_or_not_found(item.audit_required)}",
        f"- Apta para entidad nueva: {boolean_or_not_found(item.suitable_for_new_entity)}",
        f"- Riesgo de tesorería: {item.cashflow_risk}",
        f"- Motivo de viabilidad financiera: {item.financial_viability_reason}",
        f"- ¿Puede pedirla CARIBDIS directamente?: {item.participation}",
        f"- Beneficiarios: {item.beneficiaries}",
        f"- Elegibilidad de una asociación nueva: {item.new_association_eligibility}",
        f"- Requisitos: {item.requirements}",
        f"- Antigüedad/experiencia: {item.seniority_requirements} / {item.experience_requirements}",
        f"- Necesidad de socios/consorcio: {item.partners_required} / {item.consortium_required}",
        f"- Necesidad de aval: {item.guarantee_requirements}",
        f"- Gastos subvencionables: {item.eligible_expenses}",
        f"- Duración: {item.duration}",
        f"- Fondos europeos: {european_funds}",
        f"- Instrumentos de ayuda: {aid_instruments}",
        f"- Eventos administrativos: {administrative_events}",
        f"- Plazo administrativo: {item.application_deadline}",
        f"- Formularios: {forms}",
        f"- Normas y bases: {legal_bases}",
        f"- Información de contacto: {item.contact_information}",
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


def _opportunity_text(item: Opportunity) -> str:
    return " ".join(
        [
            item.title,
            item.summary,
            item.raw_text,
            item.requirements,
            item.eligible_expenses,
            item.main_theme,
            " ".join(item.caribdis_keywords),
            " ".join(item.funding_purposes),
        ]
    )


def _is_partner_opportunity(item: Opportunity) -> bool:
    return item.participation in PARTNER_PARTICIPATIONS


def _supports_association(item: Opportunity) -> bool:
    return any(
        value is True
        for value in [
            item.operating_costs_eligible,
            item.staff_costs_eligible,
            item.equipment_eligible,
            item.rent_eligible,
            item.insurance_eligible,
            item.travel_eligible,
        ]
    ) or any(
        purpose
        in {
            "Ayuda para funcionamiento",
            "Ayuda para personal",
            "Ayuda para equipamiento",
            "Ayuda para sede",
        }
        for purpose in item.funding_purposes
    )


def render_numeric_summary(
    ranked: list[Opportunity],
    eligible: list[Opportunity],
    strategic: list[Opportunity],
    discarded: list[Opportunity],
) -> list[str]:
    financial = [item for item in ranked if not item.strategic_procedure]
    counters = [
        ("Oportunidades totales", len(ranked)),
        (
            "Solicitud directa",
            sum(item.participation == "Solicitud directa" for item in eligible),
        ),
        ("Con socio", sum(_is_partner_opportunity(item) for item in eligible)),
        (
            "Aptas para entidad nueva",
            sum(item.suitable_for_new_entity is True for item in eligible),
        ),
        (
            "No aptas por antigüedad",
            sum(
                item.suitable_for_new_entity is False
                and item.minimum_seniority != NOT_FOUND
                for item in financial
            ),
        ),
        (
            "Abiertas",
            sum(normalize_text(item.status) == "abierta" for item in eligible),
        ),
        (
            "Próximas",
            sum(normalize_text(item.status) == "proxima" for item in eligible),
        ),
        (
            "Cerradas recurrentes",
            sum(
                normalize_text(item.status) == "cerrada recurrente"
                for item in eligible
            ),
        ),
        (
            "Financiación del 100 %",
            sum(
                item.funding_percentage is not None
                and item.funding_percentage >= 99.5
                for item in eligible
            ),
        ),
        (
            "Con anticipo",
            sum(
                item.advance_percentage is not None
                and item.advance_percentage > 0
                for item in eligible
            ),
        ),
        (
            "Riesgo de tesorería alto o muy alto",
            sum(item.cashflow_risk in {"Alto", "Muy alto"} for item in eligible),
        ),
        (
            "Ayudas para funcionamiento",
            sum(
                item.operating_costs_eligible is True
                or "Ayuda para funcionamiento" in item.funding_purposes
                for item in eligible
            ),
        ),
        (
            "Ayudas para proyectos",
            sum("Ayuda para proyecto" in item.funding_purposes for item in eligible),
        ),
        ("Trámites estratégicos", len(strategic)),
        ("Descartadas", len(discarded)),
    ]
    lines = ["| Indicador | Total |", "|---|---:|"]
    lines.extend(f"| {label} | {value} |" for label, value in counters)
    lines.append("")
    return lines


def render_requirements_to_prepare(opportunities: list[Opportunity]) -> list[str]:
    definitions: list[
        tuple[str, Callable[[Opportunity], bool], str]
    ] = [
        (
            "Inscripción en registros",
            lambda item: _contains(
                f"{item.requirements} {item.new_association_eligibility}",
                ["inscripción", "registro"],
            ),
            "Identificar el registro oficial, reunir documentación y tramitarlo antes del plazo.",
        ),
        (
            "Antigüedad",
            lambda item: item.minimum_seniority != NOT_FOUND,
            "Documentar la fecha de constitución y vigilar las ediciones futuras.",
        ),
        (
            "Experiencia",
            lambda item: item.previous_experience_required is True,
            "Crear un historial verificable de actividades o valorar una entidad socia.",
        ),
        (
            "Socio científico",
            lambda item: item.participation
            == "Socia de universidad o centro científico",
            "Preparar una propuesta de colaboración con una universidad o centro científico.",
        ),
        (
            "Socio municipal",
            lambda item: item.participation == "Socia de ayuntamiento",
            "Preparar una propuesta concreta para ayuntamientos del litoral andaluz.",
        ),
        (
            "Certificado digital",
            lambda item: _contains(_opportunity_text(item), ["certificado digital"]),
            "Confirmar el certificado exigido y la representación electrónica.",
        ),
        (
            "Plan de voluntariado",
            lambda item: _contains(_opportunity_text(item), ["plan de voluntariado"]),
            "Redactar y aprobar el plan cuando la convocatoria lo exija.",
        ),
        (
            "Cofinanciación",
            lambda item: (
                item.cofinancing_percentage is not None
                and item.cofinancing_percentage > 0
            )
            or item.cofinancing != NOT_FOUND,
            "Definir fuentes propias o externas y un plan de tesorería verificable.",
        ),
    ]
    lines = [
        "| Requisito | Oportunidades afectadas | Preparación recomendada |",
        "|---|---|---|",
    ]
    for label, predicate, recommendation in definitions:
        matching = [item for item in opportunities if predicate(item)]
        if matching:
            titles = ", ".join(
                f"[{markdown_text(item.title)}]({item.official_url})"
                if item.official_url
                else markdown_text(item.title)
                for item in matching
            )
        else:
            titles = NOT_FOUND
        lines.append(f"| {label} | {titles} | {recommendation} |")
    lines.append("")
    return lines


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
    eligible = _filter(
        ranked,
        lambda item: item.priority != "Descartar" and not item.strategic_procedure,
    )
    top_eligible = _filter(
        eligible,
        lambda item: item.priority != "Baja" or item.thematic_minimum_met,
    )
    top_eligible_ids = {id(item) for item in top_eligible}
    low_generic_ranking = [
        item for item in eligible if id(item) not in top_eligible_ids
    ]
    open_items = _filter(top_eligible, lambda item: normalize_text(item.status) == "abierta")
    direct_open = _filter(
        open_items,
        lambda item: item.participation == "Solicitud directa",
    )
    upcoming = _filter(top_eligible, lambda item: normalize_text(item.status) == "proxima")
    recurrent = _filter(top_eligible, lambda item: normalize_text(item.status) == "cerrada recurrente")
    strategic = _filter(ranked, lambda item: item.strategic_procedure)
    discarded = _filter(
        ranked,
        lambda item: item.priority == "Descartar" and not item.strategic_procedure,
    )
    new_entity_priority = _filter(
        top_eligible,
        lambda item: item.suitable_for_new_entity is True,
    )
    sustaining = _filter(eligible, _supports_association)
    marine_scientific = _filter(
        eligible,
        lambda item: item.thematic_minimum_met
        and _contains(
            f"{item.main_theme} {_opportunity_text(item)}",
            [
                "marina",
                "marino",
                "submarina",
                "submarino",
                "litoral",
                "ciencia ciudadana",
                "divulgación científica",
                "cultura científica",
                "educación ambiental",
            ],
        ),
    )
    social_educational = _filter(
        eligible,
        lambda item: _contains(
            f"{item.main_theme} {_opportunity_text(item)}",
            [
                "infancia",
                "menores",
                "juventud",
                "discapacidad",
                "NEAE",
                "inclusión",
                "vulnerabilidad",
                "accesibilidad",
            ],
        ),
    )
    junta = _filter(
        eligible,
        lambda item: _contains(item.source_group, ["Junta de Andalucía", "BOJA"]),
    )
    provincial_local = _filter(
        eligible,
        lambda item: _contains(
            item.source_group,
            ["Diputación", "Ayuntamiento", "Entidad local", "Municipal"],
        ),
    )
    state_bdns = _filter(
        eligible,
        lambda item: _contains(
            f"{item.source_group} {item.territory}",
            ["Estatal", "España", "BDNS"],
        ),
    )
    european = _filter(
        eligible,
        lambda item: _contains(
            f"{item.source_group} {item.territory}",
            ["Europa", "Unión Europea"],
        ),
    )
    private_funding = _filter(
        eligible,
        lambda item: _contains(
            f"{item.source_group} {item.organization_type} {item.funding_instrument}",
            [
                "Fundación privada",
                "Fundaciones privadas",
                "Donación",
                "Patrocinio",
                "Convocatoria de fundación",
                "Responsabilidad social corporativa",
                "Apoyo en especie",
            ],
        ),
    )
    partner_items = _filter(eligible, _is_partner_opportunity)
    not_ready = _filter(
        eligible,
        lambda item: item.suitable_for_new_entity is False
        or item.participation == "Vigilar y preparar requisitos",
    )
    galp_fempa = _filter(
        eligible,
        lambda item: _contains(
            f"{item.source_group} {item.title}",
            ["GALP", "GALPA", "FEMPA", "Pleamar"],
        ),
    )

    lines = [
        "# INFORME ÚNICO DE AYUDAS CARIBDIS",
        "",
        "## 1. Resumen ejecutivo",
        "",
        (
            "> **CARIBDIS es una asociación andaluza sin ánimo de lucro de nueva "
            "creación. Su viabilidad dependerá inicialmente en gran medida de "
            "subvenciones, donaciones, patrocinios, cuotas y colaboraciones. Por "
            "ello, este informe prioriza la financiación a fondo perdido, los "
            "anticipos, la cobertura de gastos de funcionamiento y las "
            "convocatorias viables para entidades nuevas.**"
        ),
        "",
        f"- Ejecución: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- Periodo revisado: {start_date.isoformat()} a {end_date.isoformat()}",
        f"- Fuentes comprobadas: {len(run.sources_checked)}",
        f"- Fuentes consultadas con éxito: {len(run.sources_succeeded)}",
        f"- Incidencias: {len(run.incidents)}",
        "",
        "### Resumen numérico",
        "",
        *render_numeric_summary(ranked, eligible, strategic, discarded),
        "### Cobertura real por fuente",
        "",
        *render_source_coverage(run),
        "### Fuentes con incidencias",
        "",
        *render_incidents(run.incidents),
        "### Fuentes pendientes de adaptación",
        "",
        *render_pending_sources(run),
        "## 2. Ayudas abiertas que CARIBDIS puede solicitar directamente",
        "",
        *render_compact_table(direct_open),
        "## 3. Ayudas prioritarias para una asociación nueva",
        "",
        *render_compact_table(new_entity_priority),
        "### Ayudas próximas o esperadas",
        "",
        *render_compact_table(upcoming, 10),
        "### Ayudas cerradas pero recurrentes",
        "",
        *render_compact_table(recurrent, 10),
        "## 4. Ayudas para sostener la asociación",
        "",
        (
            "Incluye oportunidades que cubren funcionamiento, personal, sede, "
            "seguros, gestoría, equipamiento, desplazamientos o comunicación."
        ),
        "",
        *render_compact_table(sustaining),
        "## 5. Ayudas para proyectos marinos y científicos",
        "",
        *render_compact_table(marine_scientific),
        "### Ayudas GALP, GALPA, FEMPA y Pleamar",
        "",
        *render_compact_table(galp_fempa),
        "## 6. Ayudas para infancia, juventud, discapacidad, NEAE e inclusión",
        "",
        *render_compact_table(social_educational),
        "## 7. Ayudas de la Junta de Andalucía",
        "",
        *render_compact_table(junta),
        "## 8. Ayudas de diputaciones y ayuntamientos",
        "",
        *render_compact_table(provincial_local),
        "## 9. Ayudas estatales y BDNS",
        "",
        *render_compact_table(state_bdns),
        "## 10. Ayudas europeas",
        "",
        *render_compact_table(european),
        "## 11. Donaciones, patrocinios y fundaciones privadas",
        "",
        *render_compact_table(private_funding),
        "## 12. Ayudas que exigen socio",
        "",
        *render_compact_table(partner_items),
        "## 13. Ayudas para las que CARIBDIS todavía no cumple requisitos",
        "",
        *render_compact_table(not_ready),
        "## 14. Requisitos que deben prepararse",
        "",
        *render_requirements_to_prepare(eligible),
        "## 15. Trámites estratégicos para fortalecer CARIBDIS — no son ayudas económicas",
        "",
        *render_strategic_procedures(strategic),
        "## 16. Ayudas descartadas y motivo",
        "",
        *render_discarded_table(discarded),
        "## 17. Calendario de próximos 3, 6 y 12 meses",
        "",
        *render_calendar(eligible, today),
        "## 18. Ranking general",
        "",
    ]
    if top_eligible:
        for position, item in enumerate(top_eligible, 1):
            lines.extend(render_detailed_opportunity(item, position))
        if low_generic_ranking:
            lines.extend(
                [
                    "### Otras oportunidades de prioridad Baja fuera del Top CARIBDIS",
                    "",
                    (
                        "No superan el umbral temático y se conservan solo para "
                        "consulta secundaria."
                    ),
                    "",
                ]
            )
            start_position = max(11, len(top_eligible) + 1)
            for position, item in enumerate(
                low_generic_ranking,
                start=start_position,
            ):
                lines.extend(render_detailed_opportunity(item, position))
    else:
        lines.extend(
            [
                "No se han localizado oportunidades con encaje suficiente para el Top CARIBDIS.",
                "",
            ]
        )
        if low_generic_ranking:
            lines.extend(
                [
                    "### Otras oportunidades de prioridad Baja fuera del Top CARIBDIS",
                    "",
                    (
                        "No superan el umbral temático y se conservan solo para "
                        "consulta secundaria."
                    ),
                    "",
                ]
            )
            for position, item in enumerate(low_generic_ranking, start=11):
                lines.extend(render_detailed_opportunity(item, position))

    immediate = [
        item
        for item in direct_open
        if item.priority in {"Muy alta", "Alta"}
        and item.suitable_for_new_entity is not False
    ][:5]
    lines.extend(["## 19. Recomendaciones de actuación inmediata", ""])
    if immediate:
        for item in immediate:
            lines.append(
                f"- Revisar hoy [{item.title}]({item.official_url}) y confirmar "
                f"beneficiarios, tesorería y documentación antes de {item.close_date}."
            )
    else:
        lines.append(
            "- No hay ayudas abiertas de prioridad alta verificadas; revisar las próximas "
            "ediciones y resolver primero las incidencias de fuentes."
        )
    if sustaining:
        lines.append(
            "- Priorizar las ayudas de funcionamiento y elaborar un presupuesto anual "
            "de seguros, gestoría, sede, personal, materiales y desplazamientos."
        )
    if not_ready:
        lines.append(
            "- Preparar los requisitos identificados en la sección 14 antes de la "
            "siguiente edición o formalizar una participación mediante entidad socia."
        )
    if any(normalize_text(item.status) == "abierta" for item in strategic):
        lines.append(
            "- Revisar los trámites estratégicos abiertos de la sección 15; no aportan "
            "financiación, pero pueden mejorar la elegibilidad futura de CARIBDIS."
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
