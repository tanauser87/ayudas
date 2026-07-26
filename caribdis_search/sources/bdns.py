from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from ..extractors import clean_text, normalize_text, parse_date
from ..models import NOT_FOUND, Opportunity
from .base import BaseSource, SourceContext, fetch_json


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


def record_territory(record: dict[str, Any]) -> tuple[str, str]:
    value = " ".join(str(record.get(field, "")) for field in ["nivel1", "nivel2", "nivel3", "descripcion"])
    normalized = normalize_text(value)
    for key, province in PROVINCES.items():
        if key in normalized:
            return "Andalucía", province
    if "andaluc" in normalized:
        return "Andalucía", NOT_FOUND
    return "España", NOT_FOUND


class BDNSSource(BaseSource):
    def collect(self, context: SourceContext) -> list[Opportunity]:
        opportunities: list[Opportunity] = []
        for page in range(max(1, int(self.config.get("pages", 6)))):
            payload = fetch_json(
                self.config["url"],
                context,
                self.config,
                {
                    "page": page,
                    "pageSize": int(self.config.get("page_size", 100)),
                },
            )
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
                territory, province = record_territory(record)
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
