from __future__ import annotations

import hashlib
from datetime import timedelta

import scraper_boe_boja_social as legacy

from ..extractors import extract_status
from ..models import NOT_FOUND, Opportunity
from .base import BaseSource, SourceContext


class LegacyBoeBojaSource(BaseSource):
    def __init__(self) -> None:
        super().__init__(
            {
                "id": "boe_boja",
                "name": "BOE y BOJA",
                "group": "BOE/BOJA",
                "url": "https://www.boe.es/",
                "official_domains": ["boe.es", "juntadeandalucia.es"],
                "coverage_type": "historical",
                "coverage_note": "Consulta diaria por fecha en los diarios oficiales BOE y BOJA.",
            }
        )
        self.errors: list[str] = []

    def collect(self, context: SourceContext) -> list[Opportunity]:
        opportunities: list[Opportunity] = []
        current = context.start_date
        while current <= context.end_date:
            errors: list[str] = []
            notices = legacy.collect_boe(current, context.timeout, errors)
            notices.extend(legacy.collect_boja(current, context.timeout, errors))
            results = legacy.build_results(notices, context.timeout, errors)
            self.errors.extend(f"{current.isoformat()}: {error}" for error in errors)
            for item in results:
                opportunity_id = hashlib.sha256(
                    f"{item.source}|{item.url}".encode("utf-8")
                ).hexdigest()
                combined = f"{item.title} {item.beneficiary_hint} {' '.join(item.matched_terms)}"
                opportunities.append(
                    Opportunity(
                        id=opportunity_id,
                        source_id=self.id,
                        title=item.title,
                        organization=item.entity,
                        source=item.source,
                        source_group="Estatal - BOE" if item.source == "BOE" else "Junta de Andalucía - BOJA",
                        organization_type=(
                            "Administración General del Estado"
                            if item.source == "BOE"
                            else "Administración autonómica"
                        ),
                        territory="España" if item.source == "BOE" else "Andalucía",
                        published_date=item.published_date,
                        open_date=item.open_date,
                        close_date=item.close_date,
                        status=extract_status(item.open_date, item.close_date, combined, context.today),
                        official_url=item.url,
                        bases_url=item.pdf_url or NOT_FOUND,
                        beneficiaries=item.beneficiary_hint,
                        summary=combined,
                        raw_text=combined,
                        checked_at=item.checked_at,
                        coverage_type="historical",
                        coverage_note="Edicion diaria oficial consultada por fecha.",
                        metadata_verified=True,
                    )
                )
            current += timedelta(days=1)
        return opportunities
