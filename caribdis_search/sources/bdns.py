from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from ..extractors import clean_text, normalize_text, parse_date
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

BDNS_RELEVANCE_TERMS = [
    "medio ambiente",
    "marino",
    "litoral",
    "costa",
    "biodiversidad",
    "ciencia",
    "cultura",
    "divulgacion",
    "educacion",
    "infancia",
    "menores",
    "juventud",
    "discapacidad",
    "accesibilidad",
    "inclusion",
    "vulnerabilidad",
    "voluntariado",
    "fempa",
    "galpa",
]

BDNS_GRANT_TERMS = [
    "subvencion",
    "ayuda",
    "convocatoria",
    "convenio",
    "premio",
    "patrocinio",
]


def record_territory(record: dict[str, Any]) -> tuple[str, str]:
    value = " ".join(str(record.get(field, "")) for field in ["nivel1", "nivel2", "nivel3", "descripcion"])
    normalized = normalize_text(value)
    for key, province in PROVINCES.items():
        if key in normalized:
            return "Andalucía", province
    if "andaluc" in normalized:
        return "Andalucía", NOT_FOUND
    level = normalize_text(str(record.get("nivel1") or ""))
    if "estatal" in level or level == "estado":
        return "España", NOT_FOUND
    if "local" in level or "autonom" in level:
        return "Fuera de Andalucía", NOT_FOUND
    return "España", NOT_FOUND


class BDNSSource(BaseSource):
    def collect(self, context: SourceContext) -> list[Opportunity]:
        opportunities: list[Opportunity] = []
        urls = [self.config["url"], *self.config.get("fallback_urls", [])]
        active_url = ""
        for page in range(max(1, int(self.config.get("pages", 6)))):
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
                            "page": page,
                            "pageSize": int(self.config.get("page_size", 100)),
                        },
                    )
                    active_url = url
                    break
                except (json.JSONDecodeError, OSError, ValueError, SourceError) as exc:
                    errors.append(exc)
            if payload is None:
                raise RuntimeError(f"BDNS no devolvió JSON válido: {errors[-1] if errors else 'sin detalle'}")
            for record in payload.get("content", []):
                number = str(record.get("numeroConvocatoria") or record.get("id") or "")
                if not number:
                    continue
                received = clean_text(str(record.get("fechaRecepcion") or ""))
                received_date = parse_date(received)
                if received_date and not (context.start_date <= received_date <= context.end_date):
                    continue
                title = clean_text(str(record.get("descripcion") or "Convocatoria sin título"))
                organization = " / ".join(
                    clean_text(str(record.get(field)))
                    for field in ["nivel1", "nivel2", "nivel3"]
                    if record.get(field)
                )
                normalized_title = normalize_text(title)
                if not any(term in normalized_title for term in BDNS_GRANT_TERMS):
                    continue
                if not any(term in normalize_text(f"{title} {organization}") for term in BDNS_RELEVANCE_TERMS):
                    continue
                territory, province = record_territory(record)
                if territory == "Fuera de Andalucía":
                    continue
                url = str(self.config["detail_url"]).format(numeroConvocatoria=number)
                opportunity_id = hashlib.sha256(f"bdns|{number}".encode("utf-8")).hexdigest()
                opportunities.append(
                    Opportunity(
                        id=opportunity_id,
                        title=title,
                        organization=organization or "Sistema Nacional de Publicidad de Subvenciones",
                        source=self.name,
                        source_group=self.config["group"],
                        organization_type=self.config.get("organization_type", "Administración pública"),
                        territory=territory,
                        province=province,
                        published_date=received or NOT_FOUND,
                        official_url=url,
                        summary=f"Número BDNS: {number}. Administración convocante: {organization}.",
                        checked_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                    )
                )
        return opportunities
