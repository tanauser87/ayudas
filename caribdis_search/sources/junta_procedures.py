from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from datetime import date, datetime
from typing import Any

from ..extractors import (
    clean_text,
    context_after,
    extract_money,
    extract_percentage,
    normalize_text,
    parse_date,
)
from ..identity import extract_bdns_number, extract_official_identifiers
from ..models import NOT_FOUND, Opportunity
from .base import BaseSource, SourceContext, SourceError, fetch_json


SEARCH_PATH = "/api/v0/procedures/get/search_paginations"
DETAIL_PATH = "/api/v0/procedures/{bid}"
FRONT_DETAIL_PATH = "/api/v0/procedures/frontsearchdetails/{bid}"
EU_FUNDS_PATH = "/api/v0/procedures/get/search_paginations_ffee"
SUBSIDY_FAMILY = "Familia 2. Subvenciones, becas y premios"

REQUIRED_PARAMETERS = {
    SEARCH_PATH: {
        "status",
        "topic",
        "counseling",
        "organism",
        "family",
        "activity",
        "size",
        "page",
    },
    DETAIL_PATH: {"bid"},
    FRONT_DETAIL_PATH: {"bid"},
    EU_FUNDS_PATH: {
        "status",
        "counseling",
        "organism",
        "eufunds",
        "size",
        "page",
    },
}

DEFAULT_PREFILTER_TERMS = [
    "medio ambiente",
    "agua",
    "litoral",
    "medio natural",
    "calidad ambiental",
    "cambio climatico",
    "pesca",
    "acuicultura",
    "biodiversidad",
    "asociaciones",
    "fundaciones",
    "voluntariado",
    "participacion ciudadana",
    "infancia",
    "adolescencia",
    "juventud",
    "discapacidad",
    "servicios sociales",
    "inclusion",
    "investigacion",
    "educacion",
    "cultura",
    "comunicacion social",
    "centros educativos",
    "fondos europeos",
    "fempa",
    "feder",
    "fse+",
    "feader",
    "mrr",
]

STRATEGIC_TERMS = [
    "inscripcion",
    "registro",
    "acreditacion",
    "autorizacion",
    "reconocimiento como entidad colaboradora",
    "habilitacion",
]

FUND_NAMES = {
    "FEADER": "FEADER",
    "FEAGA": "FEAGA",
    "FEDER": "FEDER",
    "FEMP": "FEMP",
    "FEMPA": "FEMPA",
    "FSE+": "FSE+",
    "FTJ": "Fondo de Transición Justa",
    "MRR": "Mecanismo de Recuperación y Resiliencia",
}

PROVINCES = {
    "almeria": "Almería",
    "cadiz": "Cádiz",
    "cordoba": "Córdoba",
    "granada": "Granada",
    "huelva": "Huelva",
    "jaen": "Jaén",
    "malaga": "Málaga",
    "sevilla": "Sevilla",
}

EVENT_TERMS = {
    "Modificación de plazo": ["modificacion de plazo", "plazos"],
    "Anuncio de subsanación": ["subsanacion", "requerimiento"],
    "Resolución publicada": ["resolucion dictada", "resuelve el procedimiento"],
    "Propuesta provisional": ["propuesta provisional", "tramite de audiencia"],
}


def analyze_openapi(specification: dict[str, Any]) -> dict[str, dict[str, Any]]:
    paths = specification.get("paths")
    if not isinstance(paths, dict):
        raise SourceError("El OpenAPI de procedimientos no contiene paths.")

    analysis: dict[str, dict[str, Any]] = {}
    for path, expected_parameters in REQUIRED_PARAMETERS.items():
        operation = paths.get(path, {}).get("get")
        if not isinstance(operation, dict):
            raise SourceError(f"El OpenAPI no documenta GET {path}.")
        parameters = {
            str(parameter.get("name"))
            for parameter in operation.get("parameters", [])
            if isinstance(parameter, dict) and parameter.get("name")
        }
        missing = expected_parameters - parameters
        if missing:
            raise SourceError(
                f"GET {path} no documenta los parámetros: {', '.join(sorted(missing))}."
            )
        analysis[path] = {
            "summary": str(operation.get("summary") or ""),
            "parameters": sorted(parameters),
            "paginated": {"page", "size"}.issubset(parameters),
        }

    schemas = specification.get("components", {}).get("schemas", {})
    families = schemas.get("_Enum_Families", {}).get("enum", [])
    if SUBSIDY_FAMILY not in families:
        raise SourceError(
            f"El OpenAPI no documenta la familia oficial {SUBSIDY_FAMILY!r}."
        )
    funds = schemas.get("_Enum_Eufunds", {}).get("enum", [])
    analysis["european_funds"] = {"values": list(funds)}
    return analysis


def _values(value: Any) -> list[str]:
    if isinstance(value, list):
        candidates = value
    elif value in (None, ""):
        candidates = []
    else:
        candidates = [value]
    result: list[str] = []
    for candidate in candidates:
        cleaned = clean_text(str(candidate or ""))
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result


def _joined(value: Any, separator: str = "; ") -> str:
    return separator.join(_values(value)) or NOT_FOUND


def _iso_date(value: Any) -> str:
    parsed = parse_date(clean_text(str(value or "")))
    return parsed.isoformat() if parsed else NOT_FOUND


def _date_values(value: Any) -> list[date]:
    result: list[date] = []
    for item in _values(value):
        parsed = parse_date(item)
        if parsed:
            result.append(parsed)
    return result


def _deadline_window(record: dict[str, Any]) -> tuple[str, str]:
    starts = _date_values(record.get("application_start_date"))
    ends = _date_values(record.get("application_end_date"))
    if ends:
        latest_index = max(range(len(ends)), key=lambda index: ends[index])
        start = starts[latest_index] if latest_index < len(starts) else None
        return (
            start.isoformat() if start else NOT_FOUND,
            ends[latest_index].isoformat(),
        )
    if starts:
        return max(starts).isoformat(), NOT_FOUND
    return NOT_FOUND, NOT_FOUND


def _years_in_record(record: dict[str, Any]) -> set[str]:
    text = " ".join(
        [
            str(record.get("title") or record.get("name") or ""),
            " ".join(_values(record.get("novelties_description"))),
        ]
    )
    return set(re.findall(r"\b(?:19|20)\d{2}\b", text))


def _is_recurrent(record: dict[str, Any]) -> bool:
    text = normalize_text(
        " ".join(
            [
                str(record.get("title") or record.get("name") or ""),
                str(record.get("description") or ""),
                " ".join(_values(record.get("novelties_description"))),
            ]
        )
    )
    return len(_years_in_record(record)) >= 2 or any(
        term in text
        for term in ["convocatoria anual", "periodicidad anual", "cada ano"]
    )


def _status(
    record: dict[str, Any],
    open_date: str,
    recurrent: bool,
    today: date,
) -> str:
    parsed_open = parse_date(open_date)
    if parsed_open and parsed_open > today:
        return "Próxima"
    state = normalize_text(str(record.get("state") or ""))
    if state == "abierto":
        return "Abierta"
    if state == "cerrado":
        return "Cerrada recurrente" if recurrent else "Cerrada"
    return "Desconocida"


def _record_text(record: dict[str, Any]) -> str:
    fields = [
        record.get("title"),
        record.get("name"),
        record.get("description"),
        record.get("topic"),
        record.get("topic_base"),
        record.get("family"),
        record.get("counseling"),
        record.get("managing_organism"),
        record.get("requirements"),
        record.get("documents"),
        record.get("application_deadline_notes"),
        record.get("eufunds"),
    ]
    fields.extend(_values(record.get("recipient_name")))
    fields.extend(_values(record.get("novelties_description")))
    fields.extend(_values(record.get("legal_basis_title")))
    return clean_text(" ".join(str(value or "") for value in fields))


def _prefilter_candidate(record: dict[str, Any], terms: list[str]) -> bool:
    text = normalize_text(_record_text(record))
    return any(normalize_text(term) in text for term in terms)


def _candidate_priority(
    record: dict[str, Any],
    terms: list[str],
    watchlist: set[str],
) -> tuple[int, int, int, int, int]:
    code = str(record.get("id") or "")
    text = normalize_text(_record_text(record))
    thematic_matches = sum(
        normalize_text(term) in text
        for term in terms
    )
    state = normalize_text(str(record.get("state") or ""))
    raw_funds = normalize_text(str(record.get("eufunds") or ""))
    has_european_funds = bool(raw_funds and raw_funds not in {"na", "-"})
    numeric_code = int(code) if code.isdigit() else 0
    return (
        0 if code in watchlist else 1,
        0 if state == "abierto" else 1,
        0 if has_european_funds else 1,
        -thematic_matches,
        -numeric_code,
    )


def _procedure_kind(record: dict[str, Any]) -> tuple[str, bool, bool]:
    family = normalize_text(str(record.get("family") or ""))
    title = normalize_text(str(record.get("title") or record.get("name") or ""))
    if normalize_text(SUBSIDY_FAMILY) in family:
        if "subvencion" in title:
            return "Subvención", True, False
        if "beca" in title:
            return "Beca", True, False
        if "premio" in title:
            return "Premio", True, False
        return "Ayuda económica", True, False

    combined = f"{family} {title}"
    strategic = any(term in combined for term in STRATEGIC_TERMS)
    if "autorizacion" in combined and "inscripcion" in combined:
        return "Autorización e inscripción", False, strategic
    if "registro" in combined or "inscripcion" in combined:
        return "Inscripción o registro", False, strategic
    if "acreditacion" in combined or "habilitacion" in combined:
        return "Acreditación o habilitación", False, strategic
    return "Procedimiento administrativo", False, strategic


def _non_competitive_record_type(text: str) -> str | None:
    normalized = normalize_text(text)
    if any(
        term in normalized
        for term in (
            "concesion directa",
            "subvencion nominativa",
            "subvenciones nominativas",
            "beneficiario unico",
        )
    ):
        return "Concesión directa"
    if "convenio con destinatario identificado" in normalized:
        return "Convenio con destinatario identificado"
    return None


def _new_association_eligibility(
    recipients: str,
    requirements: str,
    financial: bool,
) -> str:
    normalized_recipients = normalize_text(recipients)
    normalized_requirements = normalize_text(requirements)
    association_allowed = any(
        term in normalized_recipients
        for term in ["asociaciones", "organizaciones", "entidades sin animo de lucro"]
    )
    if not financial:
        return (
            "No aplica como ayuda económica; el trámite puede exigir personalidad "
            "jurídica, medios, inscripción o experiencia."
        )
    if not association_allowed:
        return "No consta que las asociaciones sin ánimo de lucro sean destinatarias."

    if (
        "modalidad de programa" in normalized_requirements
        and "modalidad de gestion" in normalized_requirements
    ):
        return (
            "Sí para la modalidad de programas si cumple las inscripciones; "
            "la gestión de centros exige funcionamiento previo."
        )
    minimum_time = re.search(
        r"\b(?:un|una|dos|tres|cuatro|cinco|\d+)\s+(?:anos?|meses?)\b",
        normalized_requirements,
    )
    experience = "experiencia" in normalized_requirements
    if minimum_time or experience:
        return (
            "No en las condiciones ordinarias si carece de historial: se exige "
            "antigüedad, funcionamiento previo o experiencia."
        )
    if any(
        term in normalized_requirements
        for term in ["estar inscrita", "estar inscritas", "registro de entidades"]
    ):
        return (
            "Sí, condicionada a cumplir previamente las inscripciones y demás "
            "requisitos sectoriales publicados."
        )
    return "Sí; no consta antigüedad mínima ni experiencia previa en la ficha API."


def _funds(record: dict[str, Any], text: str) -> list[str]:
    raw_values = _values(record.get("eufunds"))
    normalized_text = normalize_text(text)
    result: list[str] = []
    for raw in raw_values:
        for token in re.split(r"[,;|/\s]+", raw.upper()):
            if token in FUND_NAMES and FUND_NAMES[token] not in result:
                result.append(FUND_NAMES[token])
    for token, label in FUND_NAMES.items():
        normalized_token = normalize_text(token)
        if (
            re.search(
                rf"(?<![a-z0-9]){re.escape(normalized_token)}(?![a-z0-9])",
                normalized_text,
            )
            and label not in result
        ):
            result.append(label)
    return result


def _paired_links(names: Any, urls: Any) -> list[str]:
    name_values = _values(names)
    url_values = _values(urls)
    entries: list[str] = []
    for index in range(max(len(name_values), len(url_values))):
        name = name_values[index] if index < len(name_values) else ""
        url = url_values[index] if index < len(url_values) else ""
        entry = f"{name}: {url}" if name and url else name or url
        if entry and entry not in entries:
            entries.append(entry)
    return entries


def _official_links(record: dict[str, Any]) -> list[str]:
    links: list[str] = []
    for field in (
        "legal_basis_url",
        "form_url",
        "resolution_file_url",
        "document_type_url",
        "supporting_documents_url",
        "online_service_url",
        "public_consultation_url",
        "status_check_url",
    ):
        for value in _values(record.get(field)):
            if value.startswith(("http://", "https://")) and value not in links:
                links.append(re.sub(r"^http://", "https://", value))
    return links


def _province(record: dict[str, Any]) -> str:
    values = _values(record.get("resolution_province"))
    normalized = normalize_text(" ".join(values))
    matches = [
        province
        for term, province in PROVINCES.items()
        if term in normalized
    ]
    return ", ".join(dict.fromkeys(matches)) or NOT_FOUND


def _contact_information(record: dict[str, Any]) -> str:
    values: list[str] = []
    for field in (
        "processing_body_name",
        "processing_body_notes",
        "decision_body_name",
        "decision_body_notes",
        "managing_organism",
    ):
        values.extend(_values(record.get(field)))
    return "; ".join(dict.fromkeys(values))[:2_000] or NOT_FOUND


def _administrative_events(record: dict[str, Any]) -> list[str]:
    text = normalize_text(" ".join(_values(record.get("novelties_description"))))
    return [
        event
        for event, terms in EVENT_TERMS.items()
        if any(term in text for term in terms)
    ]


def _latest_relevant_date(record: dict[str, Any]) -> date | None:
    values: list[date] = []
    for field in (
        "application_end_date",
        "publication_date",
        "update_date",
        "last_updated_date",
        "novelties_date",
    ):
        values.extend(_date_values(record.get(field)))
    return max(values) if values else None


class JuntaProceduresSource(BaseSource):
    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.errors: list[str] = []
        self.openapi_analysis: dict[str, dict[str, Any]] = {}

    def _validate_openapi(self, context: SourceContext) -> None:
        specification = fetch_json(
            str(self.config["openapi_url"]),
            context,
            self.config,
            {},
        )
        if not isinstance(specification, dict):
            raise SourceError("La especificación OpenAPI no es un objeto JSON.")
        self.openapi_analysis = analyze_openapi(specification)
        for key in (
            "url",
            "detail_api_url",
            "front_detail_api_url",
            "eu_funds_url",
        ):
            path = urllib.parse.urlsplit(str(self.config[key])).path
            documented = path
            if key in {"detail_api_url", "front_detail_api_url"}:
                documented = re.sub(r"/\{[^/]+\}$", "/{bid}", path)
            if documented not in self.openapi_analysis:
                raise SourceError(
                    f"La ruta configurada {path} no está documentada en el OpenAPI."
                )

    def _fetch_pages(
        self,
        url: str,
        params: dict[str, Any],
        context: SourceContext,
        label: str,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        page = 0
        safety_limit = max(1, int(self.config.get("max_pages", 1_000)))
        while True:
            request_params = {**params, "page": page}
            try:
                payload = fetch_json(url, context, self.config, request_params)
            except (json.JSONDecodeError, OSError, ValueError, SourceError) as exc:
                self.errors.append(
                    f"{label}, página {page}: {type(exc).__name__}: {exc}"
                )
                break
            if not isinstance(payload, dict) or not isinstance(
                payload.get("results"), list
            ):
                self.errors.append(
                    f"{label}, página {page}: respuesta sin lista results."
                )
                break
            records.extend(
                record
                for record in payload["results"]
                if isinstance(record, dict)
            )
            pagination = payload.get("paginacion")
            total_pages = (
                pagination.get("totalPaginas")
                if isinstance(pagination, dict)
                else None
            )
            if isinstance(total_pages, int) and page + 1 >= total_pages:
                break
            if not payload["results"]:
                break
            page += 1
            if not isinstance(total_pages, int) and page >= safety_limit:
                self.errors.append(
                    f"{label}: la API omitió totalPaginas; límite de seguridad "
                    f"alcanzado en {safety_limit} páginas."
                )
                break
        return records

    def _fetch_detail(
        self,
        procedure_code: str,
        context: SourceContext,
    ) -> dict[str, Any]:
        url = str(self.config["detail_api_url"]).format(bid=procedure_code)
        payload = fetch_json(url, context, self.config, {})
        if not isinstance(payload, dict):
            raise SourceError(f"Detalle {procedure_code}: respuesta no válida.")
        results = payload.get("results")
        if payload.get("hits") != 1 or not isinstance(results, list) or len(results) != 1:
            raise SourceError(f"Detalle {procedure_code}: procedimiento no verificado.")
        record = results[0]
        if not isinstance(record, dict) or str(record.get("id")) != procedure_code:
            raise SourceError(f"Detalle {procedure_code}: identificador incoherente.")
        return record

    def _build_opportunity(
        self,
        record: dict[str, Any],
        context: SourceContext,
    ) -> Opportunity:
        procedure_code = str(record["id"])
        text = _record_text(record)
        title = clean_text(str(record.get("title") or record.get("name") or ""))
        procedure_kind, financial, strategic = _procedure_kind(record)
        non_competitive_type = _non_competitive_record_type(text)
        recurrent = _is_recurrent(record)
        open_date, close_date = _deadline_window(record)
        status = _status(record, open_date, recurrent, context.today)
        requirements = clean_text(str(record.get("requirements") or "")) or NOT_FOUND
        recipients = _joined(record.get("recipient_name"))
        official_url = str(self.config["public_url_template"]).format(
            bid=procedure_code
        )
        links = _official_links(record)
        identifiers = [f"JUNTA-PROC-{procedure_code}"]
        identifiers.extend(extract_official_identifiers(*links, text))
        bdns_number = extract_bdns_number(text, *links)
        forms = _paired_links(record.get("form_name"), record.get("form_url"))
        legal_bases = _paired_links(
            record.get("legal_basis_title"),
            record.get("legal_basis_url"),
        )
        european_funds = _funds(record, text)
        deadline_notes = _joined(record.get("application_deadline_notes"))
        deadline_type = _joined(record.get("application_deadline_type"))
        application_deadline = "; ".join(
            value
            for value in (deadline_type, deadline_notes)
            if value != NOT_FOUND
        ) or NOT_FOUND
        organization = clean_text(
            str(record.get("managing_organism") or record.get("counseling") or "")
        ) or NOT_FOUND
        bases_urls = _values(record.get("legal_basis_url"))
        application_url = clean_text(
            str(record.get("online_service_url") or "")
        ) or NOT_FOUND
        solicitability = "Trámite estratégico no económico"
        if financial:
            if non_competitive_type:
                solicitability = "Concesión directa"
            else:
                solicitability = {
                    "Abierta": "Solicitable",
                    "Próxima": "Pendiente de apertura",
                }.get(status, "Referencia histórica")

        return Opportunity(
            id=hashlib.sha256(
                f"junta-procedure|{procedure_code}".encode("utf-8")
            ).hexdigest(),
            source_id=self.id,
            source_references=[self.name],
            procedure_code=procedure_code,
            bdns_number=bdns_number,
            official_identifiers=list(dict.fromkeys(identifiers)),
            official_links=links,
            title=title or NOT_FOUND,
            organization=organization,
            counseling=clean_text(str(record.get("counseling") or ""))
            or NOT_FOUND,
            source=self.name,
            source_group=self.config["group"],
            organization_type=self.config.get(
                "organization_type", "Administración autonómica"
            ),
            territory="Andalucía",
            administrative_level="Autonómico",
            autonomous_community="Andalucía",
            province=_province(record),
            registered_date=_iso_date(record.get("created_date")),
            published_date=_iso_date(
                record.get("publication_date") or record.get("update_date")
            ),
            open_date=open_date,
            close_date=close_date,
            status=status,
            official_url=official_url,
            bases_url=bases_urls[0] if bases_urls else NOT_FOUND,
            application_url=application_url,
            total_budget=extract_money(
                text, ["presupuesto total", "dotación presupuestaria"]
            ),
            max_amount=extract_money(
                text, ["importe máximo", "cuantía máxima", "por proyecto"]
            ),
            financing_rate=extract_percentage(
                text, ["porcentaje financiable", "financiación"]
            ),
            cofinancing=context_after(
                text, ["cofinanciación", "aportación propia"], 350
            ),
            advance_payment=context_after(
                text, ["anticipo", "pago anticipado"], 350
            ),
            beneficiaries=recipients,
            requirements=requirements,
            seniority_requirements=context_after(
                requirements,
                ["antigüedad", "años de antelación", "año de antelación", "meses de los"],
                500,
            ),
            experience_requirements=context_after(
                requirements,
                ["experiencia", "funcionamiento previo", "especialización"],
                500,
            ),
            eligible_expenses=context_after(
                text,
                ["gastos subvencionables", "costes elegibles", "actuaciones subvencionables"],
                700,
            ),
            guarantee_requirements=context_after(
                text, ["aval", "garantía"], 350
            ),
            duration=context_after(
                text, ["duración", "periodo de ejecución"], 350
            ),
            european_funds=european_funds,
            aid_instruments=[procedure_kind] if financial else [],
            procedure_family=clean_text(str(record.get("family") or "")) or NOT_FOUND,
            procedure_topic=clean_text(str(record.get("topic") or "")) or NOT_FOUND,
            procedure_activity=clean_text(str(record.get("activity") or "")) or NOT_FOUND,
            procedure_kind=procedure_kind,
            application_deadline=application_deadline,
            forms=forms,
            legal_bases=legal_bases,
            contact_information=_contact_information(record),
            new_association_eligibility=_new_association_eligibility(
                recipients,
                requirements,
                financial,
            ),
            financial_opportunity=financial,
            strategic_procedure=strategic,
            record_type=non_competitive_type
            or (
                f"Procedimiento de {procedure_kind.lower()}"
                if financial
                else "Trámite estratégico"
            ),
            solicitability=solicitability,
            administrative_events=_administrative_events(record),
            detail_enriched=True,
            summary=clean_text(str(record.get("description") or ""))[:2_000],
            raw_text=text[:30_000],
            recurrent=recurrent,
            checked_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            coverage_type="api",
            coverage_note=(
                "API oficial paginada del catálogo actual; no ofrece filtro "
                "histórico por fechas."
            ),
            metadata_verified=True,
        )

    def _should_keep(
        self,
        opportunity: Opportunity,
        record: dict[str, Any],
        context: SourceContext,
        watched: bool,
    ) -> bool:
        if watched:
            return True
        if opportunity.strategic_procedure:
            return _prefilter_candidate(
                record,
                list(
                    dict.fromkeys(
                        [
                            *DEFAULT_PREFILTER_TERMS,
                            *self.config.get("prefilter_terms", []),
                        ]
                    )
                ),
            )
        if not opportunity.financial_opportunity:
            return False
        if opportunity.status in {"Abierta", "Próxima", "Cerrada recurrente"}:
            return True
        latest = _latest_relevant_date(record)
        return bool(latest and context.start_date <= latest <= context.end_date)

    def collect(self, context: SourceContext) -> list[Opportunity]:
        self._validate_openapi(context)
        page_size = max(1, int(self.config.get("page_size", 100)))
        common = {
            "status": "-",
            "counseling": "-",
            "organism": "-",
            "search_text": "-",
            "order_by": "id",
            "mode": "ASC",
            "format": "json",
            "size": page_size,
        }
        subsidy_records = self._fetch_pages(
            str(self.config["url"]),
            {
                **common,
                "topic": "-",
                "family": SUBSIDY_FAMILY,
                "activity": "-",
            },
            context,
            "Búsqueda de subvenciones",
        )
        european_records = self._fetch_pages(
            str(self.config["eu_funds_url"]),
            {**common, "eufunds": "-"},
            context,
            "Búsqueda de fondos europeos",
        )

        watchlist = {
            str(value)
            for value in self.config.get("procedure_watchlist", [])
        }
        prefilter_terms = list(
            dict.fromkeys(
                [
                    *DEFAULT_PREFILTER_TERMS,
                    *self.config.get("prefilter_terms", []),
                ]
            )
        )
        candidates: dict[str, dict[str, Any]] = {}
        for record in [*subsidy_records, *european_records]:
            code = str(record.get("id") or "")
            if not code:
                continue
            if code in watchlist or _prefilter_candidate(record, prefilter_terms):
                candidates.setdefault(code, {}).update(record)
        for code in watchlist:
            candidates.setdefault(code, {"id": code})

        max_detail_items = max(
            len(watchlist),
            int(self.config.get("max_detail_items", 100)),
        )
        ordered_candidates = sorted(
            candidates.items(),
            key=lambda item: _candidate_priority(
                item[1],
                prefilter_terms,
                watchlist,
            ),
        )
        if len(ordered_candidates) > max_detail_items:
            self.errors.append(
                "Prefiltrado Junta: "
                f"{len(ordered_candidates)} candidatos; se enriquecen los "
                f"{max_detail_items} prioritarios. Amplíe max_detail_items para "
                "revisar más fichas."
            )
            ordered_candidates = ordered_candidates[:max_detail_items]

        opportunities: list[Opportunity] = []
        for code, _summary in ordered_candidates:
            try:
                detail = self._fetch_detail(code, context)
            except (json.JSONDecodeError, OSError, ValueError, SourceError) as exc:
                self.errors.append(
                    f"Procedimiento {code}: {type(exc).__name__}: {exc}"
                )
                continue
            opportunity = self._build_opportunity(detail, context)
            if self._should_keep(
                opportunity,
                detail,
                context,
                watched=code in watchlist,
            ):
                opportunities.append(opportunity)
        return opportunities
