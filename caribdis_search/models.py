from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


NOT_FOUND = "Dato no localizado"


@dataclass
class ScoringBreakdown:
    eligibility: int = 0
    thematic_fit: int = 0
    social_educational_fit: int = 0
    territorial_fit: int = 0
    funding_type: int = 0
    status_deadline: int = 0
    viability: int = 0
    penalties: int = 0

    @property
    def total(self) -> int:
        subtotal = (
            self.eligibility
            + self.thematic_fit
            + self.social_educational_fit
            + self.territorial_fit
            + self.funding_type
            + self.status_deadline
            + self.viability
        )
        return max(0, min(100, subtotal - self.penalties))


@dataclass
class Opportunity:
    id: str = ""
    source_id: str = ""
    source_references: list[str] = field(default_factory=list)
    procedure_code: str = NOT_FOUND
    bdns_number: str = NOT_FOUND
    official_identifiers: list[str] = field(default_factory=list)
    official_links: list[str] = field(default_factory=list)
    title: str = NOT_FOUND
    organization: str = NOT_FOUND
    counseling: str = NOT_FOUND
    source: str = NOT_FOUND
    source_group: str = NOT_FOUND
    organization_type: str = NOT_FOUND
    territory: str = NOT_FOUND
    administrative_level: str = NOT_FOUND
    autonomous_community: str = NOT_FOUND
    province: str = NOT_FOUND
    municipality: str = NOT_FOUND
    registered_date: str = NOT_FOUND
    published_date: str = NOT_FOUND
    open_date: str = NOT_FOUND
    close_date: str = NOT_FOUND
    status: str = "Desconocida"
    official_url: str = ""
    bases_url: str = NOT_FOUND
    application_url: str = NOT_FOUND
    total_budget: str = NOT_FOUND
    max_amount: str = NOT_FOUND
    financing_rate: str = NOT_FOUND
    cofinancing: str = NOT_FOUND
    advance_payment: str = NOT_FOUND
    beneficiaries: str = NOT_FOUND
    requirements: str = NOT_FOUND
    seniority_requirements: str = NOT_FOUND
    experience_requirements: str = NOT_FOUND
    staff_requirements: str = NOT_FOUND
    partners_required: str = NOT_FOUND
    consortium_required: str = NOT_FOUND
    eligible_expenses: str = NOT_FOUND
    guarantee_requirements: str = NOT_FOUND
    duration: str = NOT_FOUND
    european_funds: list[str] = field(default_factory=list)
    aid_instruments: list[str] = field(default_factory=list)
    procedure_family: str = NOT_FOUND
    procedure_topic: str = NOT_FOUND
    procedure_activity: str = NOT_FOUND
    procedure_kind: str = NOT_FOUND
    application_deadline: str = NOT_FOUND
    forms: list[str] = field(default_factory=list)
    legal_bases: list[str] = field(default_factory=list)
    contact_information: str = NOT_FOUND
    new_association_eligibility: str = NOT_FOUND
    financial_opportunity: bool = True
    strategic_procedure: bool = False
    record_type: str = "Convocatoria"
    solicitability: str = "Pendiente de verificar"
    administrative_events: list[str] = field(default_factory=list)
    detail_enriched: bool = False
    summary: str = ""
    raw_text: str = ""
    caribdis_score: int = 0
    priority: str = "Descartar"
    participation: str = "No elegible"
    score_reason: str = ""
    main_theme: str = "Sin encaje temático"
    caribdis_keywords: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    recommended_project: str = NOT_FOUND
    warnings: list[str] = field(default_factory=list)
    scoring: ScoringBreakdown = field(default_factory=ScoringBreakdown)
    checked_at: str = ""
    first_seen: str = ""
    last_seen: str = ""
    is_new: bool = False
    changes: list[str] = field(default_factory=list)
    recurrent: bool = False
    estimated_next_call: str = NOT_FOUND
    coverage_type: str = "current"
    coverage_note: str = ""
    metadata_verified: bool = False
    thematic_minimum_met: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Opportunity:
        values = dict(data)
        scoring = values.get("scoring")
        if isinstance(scoring, dict):
            values["scoring"] = ScoringBreakdown(**scoring)
        allowed = cls.__dataclass_fields__
        return cls(**{key: value for key, value in values.items() if key in allowed})


@dataclass
class Incident:
    source_id: str
    source_name: str
    message: str
    checked_at: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class SourceStatus:
    source_id: str
    source_name: str
    coverage_type: str
    coverage_note: str
    requires_adjustment: bool = False
    adjustment_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RunResult:
    opportunities: list[Opportunity] = field(default_factory=list)
    incidents: list[Incident] = field(default_factory=list)
    sources_checked: list[str] = field(default_factory=list)
    sources_succeeded: list[str] = field(default_factory=list)
    source_statuses: list[SourceStatus] = field(default_factory=list)
    pending_sources: list[SourceStatus] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
