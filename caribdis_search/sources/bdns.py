from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from ..extractors import (
    clean_text,
    context_after,
    enrich_opportunity,
    extract_money,
    extract_percentage,
    extract_status,
    normalize_text,
    parse_date,
)
from ..identity import extract_bdns_number, extract_official_identifiers
from ..models import NOT_FOUND, Opportunity
from .base import BaseSource, SourceContext, SourceError, fetch_json


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

BDNS_PREFILTER_TERMS = [
    "asociacion",
    "entidad sin animo de lucro",
    "entidades sin animo de lucro",
    "ong",
    "tercer sector",
    "medio ambiente",
    "conservacion marina",
    "biodiversidad",
    "medio marino",
    "litoral",
    "fauna",
    "flora",
    "ciencia ciudadana",
    "divulgacion cientifica",
    "cultura cientifica",
    "educacion ambiental",
    "voluntariado",
    "infancia",
    "menores",
    "juventud",
    "discapacidad",
    "accesibilidad",
    "inclusion",
    "fempa",
    "fse+",
    "fse plus",
    "feder",
    "ayudas para funcionamiento",
    "ayuda de funcionamiento",
]

EVENT_PATTERNS = [
    ("Modificación de plazo", ["modificacion de plazo", "ampliacion de plazo", "prorroga de plazo"]),
    ("Ampliación de crédito", ["ampliacion de credito", "incremento de credito"]),
    ("Anuncio de subsanación", ["subsanacion", "requerimiento de subsanacion"]),
    ("Notificación individual", ["notificacion individual", "tramite de audiencia"]),
]


def _iso_date(value: Any) -> str:
    parsed = parse_date(clean_text(str(value or "")))
    return parsed.isoformat() if parsed else NOT_FOUND


def _format_money(value: Any) -> str:
    if value in (None, ""):
        return NOT_FOUND
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return clean_text(str(value)) or NOT_FOUND
    formatted = f"{amount:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{formatted} EUR"


def _descriptions(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        if isinstance(value, dict):
            text = clean_text(
                str(
                    value.get("descripcion")
                    or value.get("nombre")
                    or value.get("codigo")
                    or ""
                )
            )
        else:
            text = clean_text(str(value))
        if text and text not in result:
            result.append(text)
    return result


def _organization(record: dict[str, Any]) -> str:
    organ = record.get("organo") if isinstance(record.get("organo"), dict) else record
    return " / ".join(
        clean_text(str(organ.get(field)))
        for field in ("nivel1", "nivel2", "nivel3")
        if organ.get(field)
    )


def _municipality(record: dict[str, Any]) -> str:
    organ = record.get("organo") if isinstance(record.get("organo"), dict) else record
    values = [clean_text(str(organ.get(field) or "")) for field in ("nivel3", "nivel2")]
    for value in values:
        match = re.search(r"\bAYUNTAMIENTO\s+(?:DE|DEL|D')\s+(.+)$", value, re.I)
        if match:
            return clean_text(match.group(1))
    level = normalize_text(str(organ.get("nivel1") or ""))
    level_two = clean_text(str(organ.get("nivel2") or ""))
    if level == "local" and level_two and "diputacion" not in normalize_text(level_two):
        return level_two
    return NOT_FOUND


def record_geography(record: dict[str, Any]) -> tuple[str, str, str, str]:
    organ = record.get("organo") if isinstance(record.get("organo"), dict) else record
    region_values = " ".join(_descriptions(record.get("regiones")))
    value = " ".join(
        [
            *(str(organ.get(field, "")) for field in ("nivel1", "nivel2", "nivel3")),
            str(record.get("descripcion", "")),
            region_values,
        ]
    )
    normalized = normalize_text(value)
    province = NOT_FOUND
    for key, name in PROVINCES.items():
        if key in normalized:
            province = name
            break
    municipality = _municipality(record)
    if "andaluc" in normalized or province != NOT_FOUND:
        return "Andalucía", province, municipality, "Andalucía"
    level = normalize_text(str(organ.get("nivel1") or ""))
    if "estatal" in level or level == "estado":
        return "España", province, municipality, NOT_FOUND
    if "local" in level or "autonom" in level:
        return "Fuera de Andalucía", province, municipality, NOT_FOUND
    return "España", province, municipality, NOT_FOUND


def record_territory(record: dict[str, Any]) -> tuple[str, str]:
    territory, province, _, _ = record_geography(record)
    return territory, province


def is_prefilter_candidate(record: dict[str, Any]) -> bool:
    text = normalize_text(
        " ".join(
            [
                str(record.get("descripcion") or ""),
                _organization(record),
                " ".join(_descriptions(record.get("tiposBeneficiarios"))),
                " ".join(_descriptions(record.get("fondos"))),
            ]
        )
    )
    return any(term in text for term in BDNS_PREFILTER_TERMS)


def _detail_text(detail: dict[str, Any]) -> str:
    announcements = detail.get("anuncios") if isinstance(detail.get("anuncios"), list) else []
    documents = detail.get("documentos") if isinstance(detail.get("documentos"), list) else []
    parts = [
        str(detail.get("descripcion") or ""),
        str(detail.get("tipoConvocatoria") or ""),
        str(detail.get("descripcionBasesReguladoras") or ""),
        str(detail.get("descripcionFinalidad") or ""),
        " ".join(_descriptions(detail.get("tiposBeneficiarios"))),
        " ".join(_descriptions(detail.get("instrumentos"))),
        " ".join(_descriptions(detail.get("fondos"))),
    ]
    for announcement in sorted(
        announcements,
        key=lambda item: str(item.get("datPublicacion") or ""),
        reverse=True,
    ):
        parts.extend(
            [
                str(announcement.get("titulo") or ""),
                str(announcement.get("texto") or ""),
                str(announcement.get("cve") or ""),
            ]
        )
    for document in documents:
        parts.append(str(document.get("descripcion") or ""))
    return clean_text(" ".join(parts))


def _administrative_events(detail: dict[str, Any]) -> list[str]:
    titles = " ".join(
        str(item.get("titulo") or "")
        for item in detail.get("anuncios", [])
        if isinstance(item, dict)
    )
    normalized = normalize_text(titles)
    return [
        event
        for event, terms in EVENT_PATTERNS
        if any(term in normalized for term in terms)
    ]


def _classify_record(
    title: str,
    detail: dict[str, Any],
    status: str,
) -> tuple[str, str]:
    title_text = normalize_text(title)
    detail_text = normalize_text(_detail_text(detail))
    combined = (
        f"{title_text} {normalize_text(str(detail.get('tipoConvocatoria') or ''))} "
        f"{detail_text}"
    )

    if any(term in title_text for term in ["licitacion", "contratacion publica", "contrato publico"]):
        return "Contrato o licitación", "No solicitables"
    if "beca" in title_text:
        return "Beca personal", "No solicitables"
    if any(
        term in combined
        for term in [
            "concesion directa",
            "subvencion nominativa",
            "beneficiario unico",
            "beneficiaria unica",
        ]
    ):
        return "Concesión directa", "Concesión directa"
    if "convenio" in title_text and any(
        term in title_text for term in ["convenio con", "convenio entre", "convenio de colaboracion"]
    ):
        return "Convenio con destinatario identificado", "Concesión directa"
    if any(
        term in detail_text
        for term in [
            "resolucion de concesion",
            "resuelve la concesion",
            "subvenciones concedidas",
            "relacion definitiva de beneficiarios",
        ]
    ):
        return "Convocatoria ya resuelta", "Convocatoria ya resuelta"
    if "bases reguladoras" in title_text and not any(
        term in title_text for term in ["se convoca", "se convocan", "y convocatoria", "convocatoria 20"]
    ):
        return "Bases reguladoras sin convocatoria abierta", "Referencia histórica"
    for event, terms in EVENT_PATTERNS:
        if any(term in title_text for term in terms):
            return event, "Referencia histórica"

    normalized_status = normalize_text(status)
    if normalized_status in {"cerrada", "cerrada recurrente"}:
        return "Convocatoria", "Referencia histórica"
    if normalized_status in {"abierta", "proxima"}:
        return "Convocatoria", "Solicitable"
    if detail.get("abierto") is True:
        return "Convocatoria", "Solicitable"
    if detail.get("abierto") is False:
        return "Convocatoria", "Referencia histórica"
    return "Convocatoria", "Pendiente de verificar"


def _official_publication_date(detail: dict[str, Any]) -> str:
    dates = [
        _iso_date(item.get("datPublicacion"))
        for item in detail.get("anuncios", [])
        if isinstance(item, dict)
    ]
    valid = [value for value in dates if value != NOT_FOUND]
    return min(valid) if valid else NOT_FOUND


def _official_links(detail: dict[str, Any]) -> list[str]:
    links: list[str] = []
    for announcement in detail.get("anuncios", []):
        if not isinstance(announcement, dict):
            continue
        link = clean_text(str(announcement.get("url") or ""))
        if link:
            link = re.sub(r"^http://", "https://", link)
            if link not in links:
                links.append(link)
    return links


class BDNSSource(BaseSource):
    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.errors: list[str] = []

    def _fetch_detail(self, number: str, context: SourceContext) -> dict[str, Any]:
        urls = [
            self.config["detail_api_url"],
            *self.config.get("detail_api_fallback_urls", []),
        ]
        errors: list[Exception] = []
        for url in urls:
            try:
                payload = fetch_json(
                    url,
                    context,
                    self.config,
                    {"numConv": number, "vpd": "GE"},
                )
                if isinstance(payload, dict):
                    return payload
                errors.append(ValueError("respuesta de detalle no es un objeto JSON"))
            except (json.JSONDecodeError, OSError, ValueError, SourceError) as exc:
                errors.append(exc)
        raise SourceError(
            f"detalle BDNS {number} no disponible: {errors[-1] if errors else 'sin detalle'}"
        )

    def _basic_opportunity(
        self,
        record: dict[str, Any],
        number: str,
        context: SourceContext,
    ) -> Opportunity:
        title = clean_text(str(record.get("descripcion") or "Convocatoria sin título"))
        organization = _organization(record)
        territory, province, municipality, community = record_geography(record)
        registered_date = _iso_date(record.get("fechaRecepcion"))
        official_url = str(self.config["detail_url"]).format(numeroConvocatoria=number)
        record_type, solicitability = _classify_record(title, {}, "Desconocida")
        return Opportunity(
            id=hashlib.sha256(f"bdns|{number}".encode("utf-8")).hexdigest(),
            source_id=self.id,
            source_references=[self.name],
            bdns_number=number,
            official_identifiers=extract_official_identifiers(title),
            title=title,
            organization=organization or "Sistema Nacional de Publicidad de Subvenciones",
            source=self.name,
            source_group=self.config["group"],
            organization_type=self.config.get(
                "organization_type", "Administración pública"
            ),
            territory=territory,
            administrative_level=clean_text(str(record.get("nivel1") or NOT_FOUND)),
            autonomous_community=community,
            province=province,
            municipality=municipality,
            registered_date=registered_date,
            published_date=registered_date,
            official_url=official_url,
            summary=f"Número BDNS: {number}. Administración convocante: {organization}.",
            raw_text=f"{title} {organization}",
            checked_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            coverage_type="api",
            coverage_note="API oficial BDNS paginada y filtrada por fecha.",
            record_type=record_type,
            solicitability=solicitability,
        )

    def _enrich(
        self,
        opportunity: Opportunity,
        detail: dict[str, Any],
        context: SourceContext,
    ) -> Opportunity:
        text = _detail_text(detail)
        organ = detail.get("organo") if isinstance(detail.get("organo"), dict) else {}
        detail_number = extract_bdns_number(detail.get("codigoBDNS"), opportunity.bdns_number)
        if detail_number != NOT_FOUND:
            opportunity.bdns_number = detail_number
            opportunity.id = hashlib.sha256(
                f"bdns|{detail_number}".encode("utf-8")
            ).hexdigest()

        title = clean_text(str(detail.get("descripcion") or ""))
        if title:
            opportunity.title = title
        organization = _organization(detail)
        if organization:
            opportunity.organization = organization
        territory, province, municipality, community = record_geography(detail)
        opportunity.territory = territory
        opportunity.administrative_level = clean_text(
            str(organ.get("nivel1") or opportunity.administrative_level)
        )
        opportunity.autonomous_community = community
        opportunity.province = province
        opportunity.municipality = municipality

        registered_date = _iso_date(detail.get("fechaRecepcion"))
        if registered_date != NOT_FOUND:
            opportunity.registered_date = registered_date
        publication_date = _official_publication_date(detail)
        opportunity.published_date = (
            publication_date
            if publication_date != NOT_FOUND
            else opportunity.registered_date
        )

        extracted = Opportunity(official_url=opportunity.official_url)
        enrich_opportunity(extracted, text, context.today)
        explicit_open = _iso_date(detail.get("fechaInicioSolicitud"))
        explicit_close = _iso_date(detail.get("fechaFinSolicitud"))
        opportunity.open_date = (
            explicit_open if explicit_open != NOT_FOUND else extracted.open_date
        )
        opportunity.close_date = (
            explicit_close if explicit_close != NOT_FOUND else extracted.close_date
        )
        opportunity.status = extract_status(
            opportunity.open_date,
            opportunity.close_date,
            text,
            context.today,
        )
        if detail.get("abierto") is True and opportunity.status == "Desconocida":
            opportunity.status = "Abierta"
        elif detail.get("abierto") is False and opportunity.status != "Próxima":
            opportunity.status = "Cerrada"

        beneficiaries = _descriptions(detail.get("tiposBeneficiarios"))
        beneficiary_context = context_after(
            text,
            ["beneficiarios", "beneficiarias", "entidades solicitantes", "podrán solicitar"],
            700,
        )
        if beneficiary_context != NOT_FOUND:
            beneficiaries.append(beneficiary_context)
        opportunity.beneficiaries = "; ".join(dict.fromkeys(beneficiaries)) or NOT_FOUND
        opportunity.requirements = context_after(
            text,
            ["requisitos", "deberán cumplir", "condiciones de las entidades"],
            600,
        )
        opportunity.seniority_requirements = context_after(
            text,
            ["antigüedad", "constituidas desde", "fecha de constitución"],
            350,
        )
        opportunity.experience_requirements = context_after(
            text,
            ["experiencia previa", "experiencia acreditada", "años de experiencia"],
            350,
        )
        opportunity.total_budget = _format_money(detail.get("presupuestoTotal"))
        opportunity.max_amount = extract_money(
            text,
            ["importe máximo", "cuantía máxima", "por proyecto", "por solicitud"],
        )
        opportunity.financing_rate = extract_percentage(
            text,
            ["porcentaje financiable", "financiación", "coste subvencionable"],
        )
        opportunity.cofinancing = context_after(
            text, ["cofinanciación", "aportación propia"], 350
        )
        opportunity.advance_payment = context_after(
            text, ["anticipo", "pago anticipado"], 350
        )
        opportunity.guarantee_requirements = context_after(
            text, ["aval", "garantía", "constitución de garantía"], 350
        )
        opportunity.eligible_expenses = context_after(
            text,
            ["gastos subvencionables", "costes elegibles", "gastos elegibles"],
            700,
        )
        opportunity.duration = context_after(
            text, ["duración", "periodo de ejecución"], 350
        )

        bases_url = clean_text(str(detail.get("urlBasesReguladoras") or ""))
        if bases_url:
            opportunity.bases_url = bases_url
        application_url = clean_text(str(detail.get("sedeElectronica") or ""))
        if application_url:
            opportunity.application_url = application_url
        opportunity.official_links = _official_links(detail)
        opportunity.official_identifiers = extract_official_identifiers(
            *opportunity.official_links,
            *(
                item.get("cve")
                for item in detail.get("anuncios", [])
                if isinstance(item, dict)
            ),
            text,
        )

        funds = _descriptions(detail.get("fondos"))
        if detail.get("mrr") is True:
            funds.append("Mecanismo de Recuperación y Resiliencia")
        normalized_text = normalize_text(text)
        for name, terms in {
            "FEMPA": ["fempa"],
            "FSE+": ["fse+", "fse plus", "fondo social europeo plus"],
            "FEDER": ["feder", "fondo europeo de desarrollo regional"],
        }.items():
            if any(term in normalized_text for term in terms):
                funds.append(name)
        opportunity.european_funds = list(dict.fromkeys(funds))
        opportunity.aid_instruments = _descriptions(detail.get("instrumentos"))
        opportunity.administrative_events = _administrative_events(detail)
        opportunity.raw_text = text[:30_000]
        opportunity.summary = " ".join(
            [
                f"Número BDNS: {opportunity.bdns_number}.",
                f"Tipo: {detail.get('tipoConvocatoria') or NOT_FOUND}.",
                f"Finalidad: {detail.get('descripcionFinalidad') or NOT_FOUND}.",
                f"Organismo: {opportunity.organization}.",
            ]
        )
        opportunity.record_type, opportunity.solicitability = _classify_record(
            opportunity.title,
            detail,
            opportunity.status,
        )
        opportunity.metadata_verified = True
        opportunity.detail_enriched = True
        return opportunity

    def collect(self, context: SourceContext) -> list[Opportunity]:
        opportunities: list[Opportunity] = []
        seen_numbers: set[str] = set()
        urls = [self.config["url"], *self.config.get("fallback_urls", [])]
        active_url = ""
        page = 0
        safety_page_limit = max(1, int(self.config.get("max_pages", 1_000)))
        while True:
            payload = None
            errors: list[Exception] = []
            candidate_urls = (
                [active_url, *(url for url in urls if url != active_url)]
                if active_url
                else urls
            )
            for url in candidate_urls:
                try:
                    payload = fetch_json(
                        url,
                        context,
                        self.config,
                        {
                            "vpd": "GE",
                            "fechaDesde": context.start_date.strftime("%d/%m/%Y"),
                            "fechaHasta": context.end_date.strftime("%d/%m/%Y"),
                            "page": page,
                            "pageSize": int(self.config.get("page_size", 100)),
                            "order": "fechaRecepcion",
                            "direccion": "desc",
                        },
                    )
                    active_url = url
                    break
                except (json.JSONDecodeError, OSError, ValueError, SourceError) as exc:
                    errors.append(exc)
            if not isinstance(payload, dict):
                raise RuntimeError(
                    f"BDNS no devolvió JSON válido: {errors[-1] if errors else 'sin detalle'}"
                )

            content = payload.get("content", [])
            for record in content:
                if not isinstance(record, dict):
                    continue
                number = extract_bdns_number(
                    record.get("numeroConvocatoria"),
                    record.get("codigoBDNS"),
                    record.get("id"),
                    record.get("descripcion"),
                )
                if number == NOT_FOUND or number in seen_numbers:
                    continue
                seen_numbers.add(number)
                received_date = parse_date(
                    clean_text(str(record.get("fechaRecepcion") or ""))
                )
                if received_date and not (
                    context.start_date <= received_date <= context.end_date
                ):
                    continue
                if not is_prefilter_candidate(record):
                    continue
                territory, _, _, _ = record_geography(record)
                if territory == "Fuera de Andalucía":
                    continue

                opportunity = self._basic_opportunity(record, number, context)
                try:
                    detail = self._fetch_detail(number, context)
                    opportunity = self._enrich(opportunity, detail, context)
                except Exception as exc:
                    message = f"Ficha {number}: {type(exc).__name__}: {exc}"
                    opportunity.warnings.append(
                        "No se pudo enriquecer la ficha BDNS; se conserva el registro básico."
                    )
                    self.errors.append(message)
                opportunities.append(opportunity)

            if payload.get("last") is True or not content:
                break
            total_pages = payload.get("totalPages")
            if isinstance(total_pages, int) and page + 1 >= total_pages:
                break
            page += 1
            if not isinstance(total_pages, int) and page >= safety_page_limit:
                self.errors.append(
                    "La API BDNS no indicó totalPages; se detuvo la paginación "
                    f"en el límite de seguridad de {safety_page_limit} páginas."
                )
                break
        return opportunities
