from __future__ import annotations

import re
import unicodedata
from datetime import date

from .models import NOT_FOUND, Opportunity, ScoringBreakdown


MARINE_TERMS = {
    "conservación marina": 9,
    "biodiversidad marina": 9,
    "fauna submarina": 9,
    "flora submarina": 9,
    "fauna marina": 7,
    "flora marina": 7,
    "especies marinas": 7,
    "hábitats marinos": 9,
    "fondos marinos": 7,
    "praderas marinas": 9,
    "praderas submarinas": 9,
    "algas": 3,
    "vegetación marina": 4,
    "medio marino": 5,
    "ecosistemas marinos": 5,
    "ecosistemas costeros": 4,
    "litoral": 3,
    "costas": 3,
    "playas": 2,
    "residuos marinos": 5,
    "contaminación marina": 5,
    "restauración marina": 9,
    "cambio climático": 3,
    "economía azul": 3,
    "fempa": 4,
    "pleamar": 4,
}

SCIENCE_EDUCATION_TERMS = {
    "ciencia ciudadana": 5,
    "investigación participativa": 4,
    "educación ambiental": 5,
    "divulgación científica": 5,
    "cultura científica": 5,
    "materiales educativos": 3,
    "materiales audiovisuales": 3,
    "talleres científicos": 4,
    "talleres ambientales": 4,
    "talleres educativos": 4,
}

SOCIAL_TERMS = {
    "menores": 3,
    "infancia": 3,
    "juventud": 2,
    "vulnerabilidad": 3,
    "vulnerabilidad social": 4,
    "discapacidad": 3,
    "neae": 4,
    "necesidades específicas de apoyo educativo": 4,
    "accesibilidad": 3,
    "inclusión": 2,
    "inclusión social": 3,
}

TERRITORY_TERMS = {
    "litoral andaluz": 10,
    "andalucía": 10,
    "almería": 9,
    "cádiz": 9,
    "huelva": 9,
    "málaga": 9,
    "sevilla": 9,
    "córdoba": 8,
    "granada": 8,
    "jaén": 8,
    "españa": 7,
    "estatal": 7,
    "unión europea": 6,
    "europa": 6,
}

EXCLUSIVE_OTHER_TERRITORIES = [
    "aragón",
    "asturias",
    "islas baleares",
    "baleares",
    "canarias",
    "cantabria",
    "castilla-la mancha",
    "castilla la mancha",
    "castilla y león",
    "cataluña",
    "comunidad de madrid",
    "comunitat valenciana",
    "comunidad valenciana",
    "extremadura",
    "galicia",
    "la rioja",
    "murcia",
    "navarra",
    "país vasco",
    "ceuta",
    "melilla",
]

DIRECT_ELIGIBILITY_TERMS = [
    "asociaciones sin ánimo de lucro",
    "entidades sin ánimo de lucro",
    "organizaciones sin ánimo de lucro",
    "entidades del tercer sector",
    "asociaciones",
    "fundaciones y asociaciones",
    "ong",
]

PARTNER_RULES = [
    (
        r"\b(?:solo|exclusivamente|únicamente).{0,35}\bayuntamientos?\b",
        "Socia de ayuntamiento",
        "beneficiarios limitados a ayuntamientos",
    ),
    (
        r"\b(?:solo|exclusivamente|únicamente).{0,35}\b(?:universidades|centros? de investigación)\b",
        "Socia de universidad o centro científico",
        "beneficiarios limitados a universidades o centros científicos",
    ),
    (
        r"\b(?:consorcio|consortium)\b.{0,80}\b(?:internacional|europeo|tres países|3 países)\b",
        "Socia de consorcio europeo",
        "exige consorcio internacional",
    ),
    (
        r"\b(?:horizon|life|interreg)\b.{0,160}\b(?:consorcio|consortium|tres países|3 países|three countries)\b",
        "Socia de consorcio europeo",
        "exige consorcio europeo",
    ),
    (
        r"\b(?:solo|exclusivamente|únicamente).{0,35}\b(?:empresas|autónomos)\b",
        "Solo con socio",
        "beneficiarios limitados a empresas o autónomos",
    ),
    (
        r"\b(?:solo|exclusivamente|únicamente).{0,35}\b(?:organismos públicos|entidades públicas)\b",
        "Solo con socio",
        "beneficiarios limitados a organismos públicos",
    ),
    (
        r"\b(?:solo|exclusivamente|únicamente).{0,35}\b(?:pescadores|armadores|propietarios de buques)\b",
        "Solo con socio",
        "beneficiarios limitados al sector pesquero",
    ),
]

HARD_EXCLUSIONS = [
    (
        r"\bconcesión directa\b",
        "concesión directa no competitiva",
    ),
    (r"\bbeneficiari[oa]\s+únic[oa]\b", "beneficiario único ya nombrado"),
    (r"\bsubvenci(?:ón|on)(?:es)?\s+nominativa", "subvención nominativa"),
    (r"\bconvenio(?:\s+de\s+colaboración)?\s+(?:con|entre)\b", "convenio con destinatario identificado"),
    (r"\bconvocatoria\s+de\s+.{0,35}\bbecas?\b", "beca personal"),
    (r"\b(?:beca|premio)s?\s+(?:personal|individual)", "beca o premio personal"),
    (r"\bpremio\b.{0,100}\bpersona\b", "premio dirigido a una persona"),
    (r"\b(?:icex|comercio exterior|exportación e inversiones)\b", "comercio exterior"),
    (
        r"\b(?:contratos?|ayudas?|investigación)\s+(?:pre|post)doctorales?\b",
        "investigación doctoral o postdoctoral",
    ),
    (r"\b(?:ministerio|industria)\s+de\s+defensa\b", "sector de defensa"),
    (r"\b(?:licitación|contratación pública|contrato público)\b", "contratación pública"),
    (r"\bnombramientos?\b", "nombramiento"),
]

PROJECTS = {
    "Conservación y biodiversidad marina": (
        "Guardianes del Litoral Andaluz: seguimiento participativo de especies, "
        "hábitats y residuos marinos."
    ),
    "Ciencia ciudadana y educación ambiental": (
        "Aulas Azules CARIBDIS: ciencia ciudadana, talleres ambientales y materiales "
        "audiovisuales accesibles."
    ),
    "Inclusión, infancia y juventud": (
        "Océano Inclusivo: talleres científicos marinos para menores, alumnado NEAE "
        "y jóvenes en situación de vulnerabilidad."
    ),
    "Voluntariado y participación": (
        "Red de Voluntariado Azul: formación y acciones comunitarias de conservación litoral."
    ),
}

THEMATIC_MARINE_MINIMUM = {
    "conservación marina",
    "biodiversidad marina",
    "fauna submarina",
    "flora submarina",
    "fauna marina",
    "flora marina",
    "especies marinas",
    "hábitats marinos",
    "fondos marinos",
    "praderas marinas",
    "praderas submarinas",
    "algas",
    "vegetación marina",
    "medio marino",
    "ecosistemas marinos",
    "ecosistemas costeros",
    "litoral",
    "costas",
    "playas",
    "residuos marinos",
    "contaminación marina",
    "restauración marina",
}

THEMATIC_SCIENCE_MINIMUM = {
    "ciencia ciudadana",
    "investigación participativa",
    "educación ambiental",
    "divulgación científica",
    "cultura científica",
    "talleres científicos",
    "talleres ambientales",
}

DEFAULT_ENTITY_PROFILE = {
    "name": "CARIBDIS",
    "stage": "Nueva creación",
    "has_large_reserves": False,
    "can_advance_large_expenses": False,
}

FINANCIAL_INSTRUMENTS = [
    ("Apoyo en especie", ["cesión de materiales", "aportación en especie", "apoyo en especie"]),
    (
        "Responsabilidad social corporativa",
        ["responsabilidad social corporativa", "programa rsc"],
    ),
    (
        "Convocatoria de fundación",
        ["convocatoria de fundación", "fundación privada", "fundaciones privadas"],
    ),
    ("Donación", ["donación", "donaciones"]),
    ("Patrocinio", ["patrocinio", "patrocinios"]),
    ("Premio", ["premio", "premios"]),
    ("Convenio", ["convenio abierto", "convenio de colaboración"]),
    ("Contrato", ["contrato", "licitación"]),
    ("Subvención", ["subvención", "subvenciones", "grant"]),
]

EXPENSE_TERMS = {
    "operating_costs_eligible": [
        "gastos de funcionamiento",
        "gastos generales",
        "mantenimiento",
        "administración",
        "gestoría",
        "licencias",
        "comunicación",
    ],
    "staff_costs_eligible": ["gastos de personal", "costes de personal", "salarios"],
    "equipment_eligible": ["equipamiento", "equipos", "material inventariable"],
    "rent_eligible": ["alquiler de sede", "arrendamiento", "alquiler"],
    "insurance_eligible": ["seguros", "pólizas de seguro"],
    "travel_eligible": ["desplazamientos", "viajes", "dietas y locomoción"],
}

PURPOSE_TERMS = [
    ("Ayuda para funcionamiento", ["funcionamiento", "mantenimiento", "gastos generales"]),
    ("Ayuda para personal", ["gastos de personal", "costes de personal", "salarios"]),
    ("Ayuda para equipamiento", ["equipamiento", "material inventariable"]),
    ("Ayuda para sede", ["alquiler de sede", "arrendamiento de sede"]),
    ("Ayuda para proyecto", ["proyecto", "proyectos"]),
]


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(character for character in normalized if not unicodedata.combining(character))
    return re.sub(r"\s+", " ", normalized).strip().lower()


def contains_term(normalized_text: str, term: str) -> bool:
    normalized_term = normalize_text(term)
    if " " in normalized_term:
        return normalized_term in normalized_text
    return re.search(rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])", normalized_text) is not None


def matched_weighted_terms(text: str, terms: dict[str, int]) -> tuple[int, list[str]]:
    normalized = normalize_text(text)
    matches = [term for term in terms if contains_term(normalized, term)]
    return sum(terms[term] for term in matches), matches


def _percentage(value: str) -> float | None:
    if not value or value == NOT_FOUND:
        return None
    match = re.search(r"(?<!\d)(100|\d{1,2})(?:[.,](\d+))?\s*%", value)
    if not match:
        return None
    decimals = f".{match.group(2)}" if match.group(2) else ""
    return float(f"{match.group(1)}{decimals}")


def _minimum_budget(text: str) -> float | None:
    match = re.search(
        r"(?:presupuesto|importe)\s+m[ií]nimo.{0,25}?(\d[\d.]*(?:,\d+)?)\s*(euros?|€)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    value = match.group(1).replace(".", "").replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return None


def _explicit_requirement(value: str, term: str) -> bool:
    normalized = normalize_text(value)
    if not normalized or normalize_text(NOT_FOUND) == normalized:
        return False
    negative = [
        f"no se exige {term}",
        f"sin {term}",
        f"no requiere {term}",
        f"no sera necesaria {term}",
    ]
    return not any(phrase in normalized for phrase in negative)


def _infer_expense_flag(text: str, terms: list[str]) -> bool | None:
    normalized = normalize_text(text)
    for term in terms:
        normalized_term = normalize_text(term)
        negative_patterns = [
            f"no subvencionable {normalized_term}",
            f"no subvencionables {normalized_term}",
            f"excluido {normalized_term}",
            f"excluidos {normalized_term}",
            f"no se admite {normalized_term}",
            f"no se admiten {normalized_term}",
        ]
        if any(pattern in normalized for pattern in negative_patterns):
            return False
    if any(contains_term(normalized, term) for term in terms):
        return True
    return None


def infer_financial_attributes(opportunity: Opportunity, text: str | None = None) -> Opportunity:
    combined = text or " ".join(
        [
            opportunity.title,
            opportunity.summary,
            opportunity.raw_text,
            opportunity.financing_rate,
            opportunity.cofinancing,
            opportunity.advance_payment,
            opportunity.eligible_expenses,
            opportunity.guarantee_requirements,
            opportunity.seniority_requirements,
            opportunity.experience_requirements,
            opportunity.new_association_eligibility,
            " ".join(opportunity.aid_instruments),
            " ".join(opportunity.european_funds),
        ]
    )
    normalized = normalize_text(combined)

    if opportunity.funding_instrument == NOT_FOUND:
        for instrument, terms in FINANCIAL_INSTRUMENTS:
            if any(contains_term(normalized, term) for term in terms):
                opportunity.funding_instrument = instrument
                break
        else:
            opportunity.funding_instrument = "Otro"
    if opportunity.funding_instrument not in opportunity.aid_instruments:
        opportunity.aid_instruments.append(opportunity.funding_instrument)

    if opportunity.funding_percentage is None:
        opportunity.funding_percentage = _percentage(opportunity.financing_rate)
        if opportunity.funding_percentage is None:
            financing_match = re.search(
                r"(?:financiaci[oó]n|porcentaje financiable|financia).{0,35}?"
                r"(100|\d{1,2})(?:[.,]\d+)?\s*%",
                combined,
                flags=re.IGNORECASE,
            )
            if financing_match:
                opportunity.funding_percentage = float(financing_match.group(1))

    if opportunity.cofinancing_percentage is None:
        opportunity.cofinancing_percentage = _percentage(opportunity.cofinancing)
        if (
            opportunity.cofinancing_percentage is None
            and opportunity.funding_percentage is not None
        ):
            opportunity.cofinancing_percentage = max(
                0.0, 100.0 - opportunity.funding_percentage
            )

    if opportunity.advance_percentage is None:
        opportunity.advance_percentage = _percentage(opportunity.advance_payment)
        if opportunity.advance_percentage is None and any(
            phrase in normalized for phrase in ["sin anticipo", "no se preve anticipo"]
        ):
            opportunity.advance_percentage = 0.0

    if opportunity.advance_guarantee_required is None:
        guarantee_text = normalize_text(
            f"{opportunity.guarantee_requirements} {combined}"
        )
        if any(
            phrase in guarantee_text
            for phrase in ["sin aval", "no se exige aval", "exento de garantia"]
        ):
            opportunity.advance_guarantee_required = False
        elif any(
            phrase in guarantee_text
            for phrase in ["aval", "garantia para el anticipo", "garantia del anticipo"]
        ):
            opportunity.advance_guarantee_required = True

    if opportunity.reimbursement_only is None:
        reimbursement_patterns = [
            r"pago.{0,45}(?:despu[eé]s|tras|una vez).{0,30}justifica",
            r"abono.{0,45}(?:despu[eé]s|tras|una vez).{0,30}justifica",
            r"pago por reembolso",
            r"previa justificaci[oó]n",
        ]
        if any(re.search(pattern, combined, flags=re.IGNORECASE) for pattern in reimbursement_patterns):
            opportunity.reimbursement_only = True
        elif opportunity.advance_percentage is not None and opportunity.advance_percentage > 0:
            opportunity.reimbursement_only = False

    expense_text = f"{opportunity.eligible_expenses} {combined}"
    for field_name, terms in EXPENSE_TERMS.items():
        if getattr(opportunity, field_name) is None:
            setattr(opportunity, field_name, _infer_expense_flag(expense_text, terms))

    if opportunity.minimum_seniority == NOT_FOUND:
        if opportunity.seniority_requirements != NOT_FOUND:
            opportunity.minimum_seniority = opportunity.seniority_requirements
        else:
            seniority_match = re.search(
                r"antig[uü]edad\s+m[ií]nima.{0,35}(?:a[nñ]os?|meses?)",
                combined,
                flags=re.IGNORECASE,
            )
            if seniority_match:
                opportunity.minimum_seniority = seniority_match.group(0)

    if opportunity.previous_experience_required is None:
        experience_text = (
            opportunity.experience_requirements
            if opportunity.experience_requirements != NOT_FOUND
            else combined
        )
        normalized_experience = normalize_text(experience_text)
        if any(
            phrase in normalized_experience
            for phrase in ["no se exige experiencia", "sin experiencia previa"]
        ):
            opportunity.previous_experience_required = False
        elif re.search(
            r"(?:experiencia|especializaci[oó]n).{0,45}"
            r"(?:obligatoria|acreditada|m[ií]nima|requerida|previa)",
            experience_text,
            flags=re.IGNORECASE,
        ):
            opportunity.previous_experience_required = True

    if opportunity.minimum_project_budget is None:
        opportunity.minimum_project_budget = _minimum_budget(combined)

    if opportunity.audit_required is None:
        if any(
            phrase in normalized
            for phrase in ["auditoria obligatoria", "informe de auditor", "auditor de cuentas"]
        ):
            opportunity.audit_required = True
        elif "no se exige auditoria" in normalized:
            opportunity.audit_required = False

    if opportunity.suitable_for_new_entity is None:
        new_entity = normalize_text(opportunity.new_association_eligibility)
        if new_entity.startswith(("no", "no apta", "no elegible")):
            opportunity.suitable_for_new_entity = False
        elif new_entity.startswith(("si", "apta")):
            opportunity.suitable_for_new_entity = True
        elif _explicit_requirement(opportunity.minimum_seniority, "antiguedad"):
            opportunity.suitable_for_new_entity = False
        elif opportunity.previous_experience_required is True:
            opportunity.suitable_for_new_entity = False

    purposes = list(opportunity.funding_purposes)
    for purpose, terms in PURPOSE_TERMS:
        if any(contains_term(normalized, term) for term in terms):
            purposes.append(purpose)
    if opportunity.european_funds:
        purposes.append("Financiación europea")
    opportunity.funding_purposes = list(dict.fromkeys(purposes))
    return opportunity


def status_points(status: str) -> int:
    normalized = normalize_text(status)
    if normalized == "abierta":
        return 10
    if normalized == "proxima":
        return 8
    if normalized == "cerrada recurrente":
        return 5
    if normalized == "cerrada":
        return 0
    return 2


def priority_for_score(score: int) -> str:
    if score >= 85:
        return "Muy alta"
    if score >= 70:
        return "Alta"
    if score >= 50:
        return "Media"
    if score >= 25:
        return "Baja"
    return "Descartar"


def _eligibility(text: str) -> tuple[int, str, list[str], bool]:
    normalized = normalize_text(text)
    exclusions = [
        label
        for pattern, label in HARD_EXCLUSIONS
        if re.search(normalize_text(pattern), normalized)
    ]
    if exclusions:
        return 0, "No elegible", exclusions, True

    for pattern, participation, risk in PARTNER_RULES:
        if re.search(normalize_text(pattern), normalized):
            return 15, participation, [risk], False

    if any(contains_term(normalized, term) for term in DIRECT_ELIGIBILITY_TERMS):
        return 25, "Solicitud directa", [], False
    return 5, "Solo con socio", ["elegibilidad de asociaciones no confirmada"], False


def _territorial_points(opportunity: Opportunity, text: str) -> int:
    combined = f"{opportunity.territory} {opportunity.province} {opportunity.municipality} {text}"
    normalized = normalize_text(combined)
    scores = [points for term, points in TERRITORY_TERMS.items() if contains_term(normalized, term)]
    return max(scores, default=0)


def _funding_points(opportunity: Opportunity, text: str) -> int:
    normalized = normalize_text(text)
    instrument = normalize_text(opportunity.funding_instrument)
    if instrument == "subvencion":
        return 10
    if instrument == "donacion":
        return 9
    if instrument in {
        "patrocinio",
        "convocatoria de fundacion",
        "responsabilidad social corporativa",
    }:
        return 8
    if instrument == "apoyo en especie":
        return 7
    if instrument == "premio" and any(
        term in normalized for term in ["proyecto", "entidad", "asociacion"]
    ):
        return 7
    if instrument == "convenio":
        return 6
    if instrument == "contrato":
        return 0
    if any(term in normalized for term in ["a fondo perdido", "subvencion", "grant"]):
        return 10
    if any(term in normalized for term in ["ayuda", "convocatoria competitiva"]):
        return 8
    if "premio" in normalized and any(term in normalized for term in ["proyecto", "entidad", "asociacion"]):
        return 7
    if any(term in normalized for term in ["patrocinio", "convenio abierto"]):
        return 6
    return 3


def _has_seniority_barrier(opportunity: Opportunity) -> bool:
    return _explicit_requirement(opportunity.minimum_seniority, "antiguedad")


def _partner_participation(participation: str) -> bool:
    return participation in {
        "Socia de ayuntamiento",
        "Socia de universidad o centro científico",
        "Socia de consorcio europeo",
        "Solo con socio",
        "Participación mediante entidad socia",
    }


def _adjust_new_entity_participation(
    opportunity: Opportunity,
    participation: str,
) -> tuple[str, bool, list[str]]:
    risks: list[str] = []
    if opportunity.suitable_for_new_entity is not False:
        return participation, False, risks

    if _partner_participation(participation):
        risks.append("CARIBDIS debe participar mediante una entidad consolidada")
        return participation, False, risks

    partners = normalize_text(
        f"{opportunity.partners_required} {opportunity.consortium_required}"
    )
    if partners and partners != normalize_text(f"{NOT_FOUND} {NOT_FOUND}"):
        risks.append("CARIBDIS debe participar mediante una entidad consolidada")
        return "Participación mediante entidad socia", False, risks

    preparable = (
        opportunity.recurrent
        or normalize_text(opportunity.status) in {"proxima", "cerrada recurrente"}
        or opportunity.estimated_next_call != NOT_FOUND
        or "proxima edicion" in normalize_text(opportunity.new_association_eligibility)
    )
    if preparable:
        risks.append(
            "debe preparar antigüedad, experiencia o inscripción para la próxima edición"
        )
        return "Vigilar y preparar requisitos", False, risks

    risks.append(
        "un requisito oficial impide solicitar la edición actual como entidad nueva"
    )
    return "No elegible", True, risks


def _cashflow_risk(
    opportunity: Opportunity,
    profile: dict[str, object],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    funding = opportunity.funding_percentage
    cofinancing = opportunity.cofinancing_percentage
    advance = opportunity.advance_percentage
    no_reserves = not bool(profile.get("has_large_reserves", False))
    cannot_advance = not bool(profile.get("can_advance_large_expenses", False))
    high_budget = bool(
        opportunity.minimum_project_budget is not None
        and opportunity.minimum_project_budget >= 50_000
    )

    if opportunity.advance_guarantee_required is True:
        reasons.append("el anticipo exige aval")
    if opportunity.reimbursement_only is True:
        reasons.append("el pago se realiza después de justificar")
    if cofinancing is not None and cofinancing > 30:
        reasons.append(f"cofinanciación propia del {cofinancing:g} %")
    if high_budget:
        reasons.append("presupuesto mínimo elevado")

    if (
        opportunity.advance_guarantee_required is True
        and (
            opportunity.reimbursement_only is True
            or high_budget
            or (cofinancing or 0) > 30
        )
    ) or (
        (cofinancing or 0) > 30
        and (advance is None or advance == 0)
        and no_reserves
    ):
        return "Muy alto", reasons
    if (
        opportunity.reimbursement_only is True
        or advance == 0
        or (cofinancing is not None and cofinancing > 30)
        or (high_budget and (no_reserves or cannot_advance))
    ):
        if cannot_advance:
            reasons.append("CARIBDIS no puede adelantar gastos elevados")
        return "Alto", reasons
    if (
        cofinancing is not None
        and 20 <= cofinancing <= 30
    ) or (
        advance is not None and 0 < advance < 50
    ) or funding is None or advance is None:
        return "Medio", reasons
    if funding is not None and funding >= 90 and advance >= 50:
        return "Bajo", reasons
    return "Medio", reasons


def _viability_points(
    opportunity: Opportunity,
    participation: str,
    profile: dict[str, object],
) -> tuple[int, list[str], str]:
    reasons: list[str] = []
    consortium_value = normalize_text(opportunity.consortium_required)
    affirmative_consortium = (
        opportunity.consortium_required != NOT_FOUND
        and not consortium_value.startswith(("no ", "no se ", "sin "))
    )
    funding = opportunity.funding_percentage
    cofinancing = opportunity.cofinancing_percentage
    advance = opportunity.advance_percentage

    if funding is not None and funding >= 95:
        points = 5
        reasons.append(f"financiación del {funding:g} %")
    elif funding is not None and funding >= 70:
        points = 4 if advance is not None and advance > 0 else 3
        reasons.append(f"financiación del {funding:g} %")
    elif cofinancing is not None and 20 <= cofinancing <= 30:
        points = 3
        reasons.append(f"cofinanciación del {cofinancing:g} %")
    elif funding is not None:
        points = 2
        reasons.append(f"financiación limitada al {funding:g} %")
    else:
        points = 5
        reasons.append(
            "sin condiciones financieras adversas publicadas; porcentaje por confirmar"
        )

    if advance is not None and advance > 0:
        reasons.append(f"anticipo del {advance:g} %")
        if funding is not None and funding >= 70:
            points = max(points, 4)
    elif advance == 0:
        reasons.append("sin anticipo")

    routine_expenses = [
        opportunity.operating_costs_eligible,
        opportunity.staff_costs_eligible,
        opportunity.equipment_eligible,
        opportunity.rent_eligible,
        opportunity.insurance_eligible,
        opportunity.travel_eligible,
    ]
    if sum(value is True for value in routine_expenses) >= 2:
        points = min(5, points + 1)
        reasons.append("admite varios gastos habituales de la asociación")

    if participation != "Solicitud directa":
        points = min(points, 3)
        reasons.append("requiere preparación o participación con socio")
    if affirmative_consortium:
        points = min(points, 2)
        reasons.append("exige coordinación de consorcio")
    if cofinancing is not None and cofinancing > 30:
        points = min(points, 1)
        reasons.append(f"cofinanciación superior al 30 % ({cofinancing:g} %)")
    if opportunity.reimbursement_only is True:
        points = min(points, 2)
        reasons.append("pago únicamente tras la justificación")
    if opportunity.advance_guarantee_required is True:
        points = min(points, 1)
        reasons.append("exige aval para el anticipo")
    if _has_seniority_barrier(opportunity):
        points = min(points, 1)
        reasons.append("exige antigüedad mínima")
    if opportunity.previous_experience_required is True:
        points = min(points, 1)
        reasons.append("exige experiencia previa")
    if opportunity.audit_required is True:
        audit_cap = 1 if (opportunity.minimum_project_budget or 0) >= 50_000 else 2
        points = min(points, audit_cap)
        reasons.append("exige auditoría")
    if (
        opportunity.minimum_project_budget is not None
        and opportunity.minimum_project_budget >= 50_000
        and not bool(profile.get("has_large_reserves", False))
    ):
        points = min(points, 1)
        reasons.append("presupuesto mínimo elevado para una entidad sin reservas")
    if (
        (opportunity.reimbursement_only is True or advance == 0)
        and not bool(profile.get("can_advance_large_expenses", False))
    ):
        points = min(points, 2)

    opportunity.cashflow_risk, cashflow_reasons = _cashflow_risk(opportunity, profile)
    reasons.extend(cashflow_reasons)
    reason = "; ".join(dict.fromkeys(reasons)) + "."
    opportunity.financial_viability_reason = reason
    return max(0, min(5, points)), list(dict.fromkeys(reasons)), reason


def _theme(marine_score: int, science_score: int, social_score: int, text: str) -> str:
    normalized = normalize_text(text)
    if "voluntariado ambiental" in normalized:
        return "Voluntariado y participación"
    if marine_score >= science_score and marine_score >= social_score and marine_score:
        return "Conservación y biodiversidad marina"
    if science_score >= social_score and science_score:
        return "Ciencia ciudadana y educación ambiental"
    if social_score:
        return "Inclusión, infancia y juventud"
    return "Sin encaje temático"


def _meets_thematic_minimum(
    text: str,
    marine_keywords: list[str],
    science_keywords: list[str],
    social_keywords: list[str],
) -> bool:
    if any(term in THEMATIC_MARINE_MINIMUM for term in marine_keywords):
        return True
    if any(term in THEMATIC_SCIENCE_MINIMUM for term in science_keywords):
        return True
    normalized = normalize_text(text)
    explicit_environmental_activity = any(
        term in normalized
        for term in [
            "taller cientifico",
            "talleres cientificos",
            "taller ambiental",
            "talleres ambientales",
            "actividad cientifica",
            "actividades cientificas",
            "actividad ambiental",
            "actividades ambientales",
        ]
    )
    return bool(social_keywords and explicit_environmental_activity)


def score_caribdis(
    opportunity: Opportunity,
    today: date | None = None,
    entity_profile: dict[str, object] | None = None,
) -> tuple[ScoringBreakdown, dict[str, object]]:
    del today  # El estado llega normalizado por el extractor; se mantiene para facilitar pruebas futuras.
    profile = entity_profile or DEFAULT_ENTITY_PROFILE
    text = " ".join(
        [
            opportunity.title,
            opportunity.summary,
            opportunity.raw_text,
            opportunity.beneficiaries,
            opportunity.requirements,
            opportunity.record_type,
            opportunity.solicitability,
            opportunity.procedure_family,
            opportunity.procedure_topic,
            opportunity.procedure_activity,
            opportunity.procedure_kind,
            opportunity.source_group,
            opportunity.territory,
            opportunity.financing_rate,
            opportunity.cofinancing,
            opportunity.advance_payment,
            opportunity.eligible_expenses,
            opportunity.guarantee_requirements,
            opportunity.seniority_requirements,
            opportunity.experience_requirements,
            opportunity.new_association_eligibility,
            opportunity.partners_required,
            opportunity.consortium_required,
            " ".join(opportunity.aid_instruments),
            " ".join(opportunity.european_funds),
        ]
    )
    infer_financial_attributes(opportunity, text)
    eligibility, participation, eligibility_risks, hard_invalid = _eligibility(text)
    participation, new_entity_invalid, new_entity_risks = _adjust_new_entity_participation(
        opportunity,
        participation,
    )
    eligibility_risks.extend(new_entity_risks)
    if new_entity_invalid:
        hard_invalid = True
        eligibility = 0
    marine_score, marine_keywords = matched_weighted_terms(text, MARINE_TERMS)
    science_score, science_keywords = matched_weighted_terms(text, SCIENCE_EDUCATION_TERMS)
    social_score, social_keywords = matched_weighted_terms(text, SOCIAL_TERMS)
    thematic_minimum_met = _meets_thematic_minimum(
        text,
        marine_keywords,
        science_keywords,
        social_keywords,
    )
    thematic_fit = min(25, marine_score + science_score)
    social_fit = min(15, social_score)
    territorial_fit = _territorial_points(opportunity, text)
    funding_type = _funding_points(opportunity, text)
    viability, viability_risks, financial_reason = _viability_points(
        opportunity,
        participation,
        profile,
    )
    penalties = 0

    normalized_territory = normalize_text(opportunity.territory)
    allowed_territories = ["andalucia", "espana", "estatal", "union europea", "europa", "dato no localizado"]
    if normalized_territory and not any(term in normalized_territory for term in allowed_territories):
        hard_invalid = True
        eligibility = 0
        participation = "No elegible"
        eligibility_risks.append("ámbito territorial fuera de Andalucía, España o la Unión Europea")
    normalized_title = normalize_text(opportunity.title)
    normalized_text = normalize_text(text)
    normalized_solicitability = normalize_text(opportunity.solicitability)
    normalized_record_type = normalize_text(opportunity.record_type)
    if not opportunity.financial_opportunity or opportunity.strategic_procedure:
        hard_invalid = True
        eligibility = 0
        participation = "No elegible"
        eligibility_risks.append(
            "trámite estratégico o registro sin financiación económica"
        )
    if normalized_solicitability in {
        "no solicitables",
        "concesion directa",
        "convocatoria ya resuelta",
    } or normalized_record_type == "bases reguladoras sin convocatoria abierta":
        hard_invalid = True
        eligibility = 0
        participation = "No elegible"
        eligibility_risks.append(
            f"registro BDNS no solicitable: {opportunity.record_type}"
        )
    if (
        "agencia espanola de proteccion de datos" in normalized_text
        and "premio" in normalized_text
    ):
        hard_invalid = True
        eligibility = 0
        participation = "No elegible"
        eligibility_risks.append("premio de la AEPD sin encaje operativo CARIBDIS")
    if (
        any(normalize_text(territory) in normalized_title for territory in EXCLUSIVE_OTHER_TERRITORIES)
        and "andalucia" not in normalized_title
    ):
        hard_invalid = True
        eligibility = 0
        participation = "No elegible"
        eligibility_risks.append("convocatoria territorial exclusiva de otra comunidad o ciudad autónoma")
    if normalize_text(opportunity.status) == "cerrada" and not opportunity.recurrent:
        penalties += 15
        eligibility_risks.append("plazo vencido sin recurrencia confirmada")

    breakdown = ScoringBreakdown(
        eligibility=eligibility,
        thematic_fit=thematic_fit,
        social_educational_fit=social_fit,
        territorial_fit=territorial_fit,
        funding_type=funding_type,
        status_deadline=status_points(opportunity.status),
        viability=viability,
        penalties=penalties,
    )
    score = 0 if hard_invalid else breakdown.total
    if not hard_invalid and not thematic_minimum_met:
        score = min(score, 49)
        eligibility_risks.append(
            "no alcanza el umbral temático CARIBDIS; el encaje social o educativo es genérico"
        )
    priority = "Descartar" if hard_invalid else priority_for_score(score)
    if (
        normalize_text(opportunity.status) in {"proxima", "cerrada recurrente"}
        and not hard_invalid
        and participation == "Solicitud directa"
    ):
        participation = "Vigilar próxima edición"

    keywords = list(dict.fromkeys(marine_keywords + science_keywords + social_keywords))
    theme = _theme(marine_score, science_score, social_score, text)
    risks = list(dict.fromkeys(eligibility_risks + viability_risks))
    reason = (
        f"Elegibilidad {eligibility}/25, temática {thematic_fit}/25, "
        f"social/educativa {social_fit}/15, territorio {territorial_fit}/10, "
        f"financiación {funding_type}/10, estado/plazo {breakdown.status_deadline}/10 "
        f"y viabilidad financiera {viability}/5"
    )
    if penalties:
        reason += f"; penalizaciones -{penalties}"
    if not thematic_minimum_met:
        reason += "; no supera el umbral temático y la prioridad queda limitada a Baja"
    reason += f". Viabilidad: {financial_reason}"

    return breakdown, {
        "score": score,
        "priority": priority,
        "participation": participation,
        "reason": reason,
        "theme": theme,
        "keywords": keywords,
        "risks": risks,
        "recommended_project": PROJECTS.get(theme, NOT_FOUND),
        "thematic_minimum_met": thematic_minimum_met,
    }


def apply_caribdis_scoring(
    opportunity: Opportunity,
    today: date | None = None,
    entity_profile: dict[str, object] | None = None,
) -> Opportunity:
    breakdown, result = score_caribdis(
        opportunity,
        today=today,
        entity_profile=entity_profile,
    )
    opportunity.scoring = breakdown
    opportunity.caribdis_score = int(result["score"])
    opportunity.priority = str(result["priority"])
    opportunity.participation = str(result["participation"])
    opportunity.score_reason = str(result["reason"])
    opportunity.main_theme = str(result["theme"])
    opportunity.caribdis_keywords = list(result["keywords"])
    opportunity.risks = list(result["risks"])
    opportunity.recommended_project = str(result["recommended_project"])
    opportunity.thematic_minimum_met = bool(result["thematic_minimum_met"])
    return opportunity
