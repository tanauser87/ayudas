from __future__ import annotations

import hashlib
from datetime import datetime

from ..extractors import extract_status
from ..models import NOT_FOUND, Opportunity
from ..scoring import normalize_text
from .base import BaseSource, SourceContext, SourceError, fetch_text


class VerifiedMetadataSource(BaseSource):
    """Build a call from reviewed metadata after checking its official pages."""

    def __init__(self, config: dict[str, object]) -> None:
        super().__init__(config)
        self.errors: list[str] = []

    def collect(self, context: SourceContext) -> list[Opportunity]:
        self.errors = []
        metadata = dict(self.config["opportunity"])
        pages = [str(self.config["url"])]
        metadata_url = str(self.config.get("metadata_url", "")).strip()
        if metadata_url and metadata_url not in pages:
            pages.append(metadata_url)
        page_parts: list[str] = []
        for url in pages:
            try:
                page_parts.append(fetch_text(url, context, self.config))
            except Exception as exc:
                self.errors.append(f"{url}: {type(exc).__name__}: {exc}")
        if not page_parts:
            raise SourceError(
                "No se pudo verificar ninguna página oficial: "
                + "; ".join(self.errors)
            )
        page_text = " ".join(page_parts)
        normalized_page = normalize_text(page_text)
        missing_terms = [
            term
            for term in self.config.get("verification_terms", [])
            if normalize_text(str(term)) not in normalized_page
        ]
        if missing_terms:
            raise SourceError(
                "La página oficial no contiene las marcas de verificación esperadas: "
                + ", ".join(str(term) for term in missing_terms)
            )

        official_url = str(metadata.get("official_url", self.config["url"]))
        summary = " ".join(
            str(metadata.get(field, ""))
            for field in ("summary", "beneficiaries", "participation_hint", "thematic_hint")
        ).strip()
        status = extract_status(
            str(metadata.get("open_date", NOT_FOUND)),
            str(metadata.get("close_date", NOT_FOUND)),
            f"{summary} {page_text[:20_000]}",
            context.today,
        )
        return [
            Opportunity(
                id=hashlib.sha256(f"{self.id}|{official_url}".encode("utf-8")).hexdigest(),
                source_id=self.id,
                title=str(metadata["title"]),
                organization=str(metadata.get("organization", self.name)),
                source=self.name,
                source_group=str(self.config["group"]),
                organization_type=str(
                    self.config.get("organization_type", "Entidad del sector público")
                ),
                territory=str(self.config.get("territory", "España")),
                published_date=str(metadata.get("published_date", NOT_FOUND)),
                open_date=str(metadata.get("open_date", NOT_FOUND)),
                close_date=str(metadata.get("close_date", NOT_FOUND)),
                status=status,
                official_url=official_url,
                bases_url=str(metadata.get("bases_url", metadata_url or NOT_FOUND)),
                application_url=str(metadata.get("application_url", NOT_FOUND)),
                total_budget=str(metadata.get("total_budget", NOT_FOUND)),
                max_amount=str(metadata.get("max_amount", NOT_FOUND)),
                financing_rate=str(metadata.get("financing_rate", NOT_FOUND)),
                cofinancing=str(metadata.get("cofinancing", NOT_FOUND)),
                advance_payment=str(metadata.get("advance_payment", NOT_FOUND)),
                funding_instrument=str(metadata.get("funding_instrument", NOT_FOUND)),
                funding_percentage=metadata.get("funding_percentage"),
                cofinancing_percentage=metadata.get("cofinancing_percentage"),
                advance_percentage=metadata.get("advance_percentage"),
                advance_guarantee_required=metadata.get(
                    "advance_guarantee_required"
                ),
                reimbursement_only=metadata.get("reimbursement_only"),
                operating_costs_eligible=metadata.get("operating_costs_eligible"),
                staff_costs_eligible=metadata.get("staff_costs_eligible"),
                equipment_eligible=metadata.get("equipment_eligible"),
                rent_eligible=metadata.get("rent_eligible"),
                insurance_eligible=metadata.get("insurance_eligible"),
                travel_eligible=metadata.get("travel_eligible"),
                minimum_seniority=str(
                    metadata.get("minimum_seniority", NOT_FOUND)
                ),
                previous_experience_required=metadata.get(
                    "previous_experience_required"
                ),
                minimum_project_budget=metadata.get("minimum_project_budget"),
                audit_required=metadata.get("audit_required"),
                suitable_for_new_entity=metadata.get("suitable_for_new_entity"),
                funding_purposes=list(metadata.get("funding_purposes", [])),
                beneficiaries=str(metadata.get("beneficiaries", NOT_FOUND)),
                partners_required=str(metadata.get("partners_required", NOT_FOUND)),
                consortium_required=str(metadata.get("consortium_required", NOT_FOUND)),
                eligible_expenses=str(metadata.get("eligible_expenses", NOT_FOUND)),
                duration=str(metadata.get("duration", NOT_FOUND)),
                summary=summary,
                raw_text=f"{summary} {page_text[:30_000]}",
                checked_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                coverage_type=str(self.config.get("coverage_type", "current")),
                coverage_note=str(self.config.get("coverage_note", "")),
                metadata_verified=True,
            )
        ]
