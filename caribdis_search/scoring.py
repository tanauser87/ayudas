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
        r"\bconcesión directa\b.{0,140}\b(?:a favor de|a la|al|para la|para el)\b",
        "concesión directa a una entidad concreta",
    ),
    (r"\bbeneficiari[oa]\s+únic[oa]\b", "beneficiario único ya nombrado"),
    (r"\b(?:beca|premio)s?\s+(?:personal|individual)", "beca o premio personal"),
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


def _funding_points(text: str) -> int:
    normalized = normalize_text(text)
    if any(term in normalized for term in ["a fondo perdido", "subvencion", "grant"]):
        return 10
    if any(term in normalized for term in ["ayuda", "convocatoria competitiva"]):
        return 8
    if "premio" in normalized and any(term in normalized for term in ["proyecto", "entidad", "asociacion"]):
        return 7
    if any(term in normalized for term in ["patrocinio", "convenio abierto"]):
        return 6
    return 3


def _viability_points(opportunity: Opportunity, participation: str, text: str) -> tuple[int, list[str]]:
    normalized = normalize_text(text)
    risks: list[str] = []
    points = 5
    if participation != "Solicitud directa":
        points = min(points, 3)
    if opportunity.consortium_required != NOT_FOUND or "consorcio" in normalized:
        points = min(points, 2)
        risks.append("coordinación de consorcio")
    if opportunity.cofinancing != NOT_FOUND or "cofinanciacion" in normalized:
        points = min(points, 3)
        risks.append("posible cofinanciación")
    if any(term in normalized for term in ["presupuesto minimo", "experiencia previa", "antiguedad minima"]):
        points = min(points, 2)
        risks.append("requisitos de experiencia, antigüedad o presupuesto mínimo")
    return points, risks


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


def score_caribdis(opportunity: Opportunity, today: date | None = None) -> tuple[ScoringBreakdown, dict[str, object]]:
    del today  # El estado llega normalizado por el extractor; se mantiene para facilitar pruebas futuras.
    text = " ".join(
        [
            opportunity.title,
            opportunity.summary,
            opportunity.raw_text,
            opportunity.beneficiaries,
            opportunity.source_group,
            opportunity.territory,
        ]
    )
    eligibility, participation, eligibility_risks, hard_invalid = _eligibility(text)
    marine_score, marine_keywords = matched_weighted_terms(text, MARINE_TERMS)
    science_score, science_keywords = matched_weighted_terms(text, SCIENCE_EDUCATION_TERMS)
    social_score, social_keywords = matched_weighted_terms(text, SOCIAL_TERMS)
    thematic_fit = min(25, marine_score + science_score)
    social_fit = min(15, social_score)
    territorial_fit = _territorial_points(opportunity, text)
    funding_type = _funding_points(text)
    viability, viability_risks = _viability_points(opportunity, participation, text)
    penalties = 0

    normalized_territory = normalize_text(opportunity.territory)
    allowed_territories = ["andalucia", "espana", "estatal", "union europea", "europa", "dato no localizado"]
    if normalized_territory and not any(term in normalized_territory for term in allowed_territories):
        hard_invalid = True
        eligibility = 0
        participation = "No elegible"
        eligibility_risks.append("ámbito territorial fuera de Andalucía, España o la Unión Europea")
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
    priority = "Descartar" if hard_invalid else priority_for_score(score)
    if normalize_text(opportunity.status) in {"proxima", "cerrada recurrente"} and not hard_invalid:
        participation = "Vigilar próxima edición"

    keywords = list(dict.fromkeys(marine_keywords + science_keywords + social_keywords))
    theme = _theme(marine_score, science_score, social_score, text)
    risks = list(dict.fromkeys(eligibility_risks + viability_risks))
    reason = (
        f"Elegibilidad {eligibility}/25, temática {thematic_fit}/25, "
        f"social/educativa {social_fit}/15, territorio {territorial_fit}/10, "
        f"financiación {funding_type}/10, estado/plazo {breakdown.status_deadline}/10 "
        f"y viabilidad {viability}/5"
    )
    if penalties:
        reason += f"; penalizaciones -{penalties}"
    reason += "."

    return breakdown, {
        "score": score,
        "priority": priority,
        "participation": participation,
        "reason": reason,
        "theme": theme,
        "keywords": keywords,
        "risks": risks,
        "recommended_project": PROJECTS.get(theme, NOT_FOUND),
    }


def apply_caribdis_scoring(opportunity: Opportunity, today: date | None = None) -> Opportunity:
    breakdown, result = score_caribdis(opportunity, today=today)
    opportunity.scoring = breakdown
    opportunity.caribdis_score = int(result["score"])
    opportunity.priority = str(result["priority"])
    opportunity.participation = str(result["participation"])
    opportunity.score_reason = str(result["reason"])
    opportunity.main_theme = str(result["theme"])
    opportunity.caribdis_keywords = list(result["keywords"])
    opportunity.risks = list(result["risks"])
    opportunity.recommended_project = str(result["recommended_project"])
    return opportunity
