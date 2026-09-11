from __future__ import annotations

import concurrent.futures
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .models import Incident, Opportunity, RunResult, SourceStatus
from .scoring import apply_caribdis_scoring
from .sources.base import BaseSource, SourceContext
from .sources.bdns import BDNSSource
from .sources.boe_boja import LegacyBoeBojaSource
from .sources.generic import GenericPageSource
from .sources.junta_procedures import JuntaProceduresSource
from .sources.verified import VerifiedMetadataSource


def create_sources(
    config: dict[str, Any],
    source_ids: set[str] | None = None,
    include_experimental: bool = False,
) -> list[BaseSource]:
    sources: list[BaseSource] = []
    if config.get("legacy_boe_boja_enabled", True) and (not source_ids or "boe_boja" in source_ids):
        sources.append(LegacyBoeBojaSource())
    for source_config in config.get("sources", []):
        if not source_config.get("enabled", True):
            continue
        if source_ids and source_config["id"] not in source_ids:
            continue
        if source_config.get("requires_adjustment", False) and not include_experimental:
            continue
        if source_config["adapter"] == "bdns":
            sources.append(BDNSSource(source_config))
        elif source_config["adapter"] == "junta_procedures":
            sources.append(JuntaProceduresSource(source_config))
        elif source_config["adapter"] == "verified":
            sources.append(VerifiedMetadataSource(source_config))
        else:
            sources.append(GenericPageSource(source_config))
    return sources


def pending_source_statuses(
    config: dict[str, Any],
    context: SourceContext,
    source_ids: set[str] | None = None,
    include_experimental: bool = False,
) -> list[SourceStatus]:
    if include_experimental:
        return []
    statuses: list[SourceStatus] = []
    for source_config in config.get("sources", []):
        if not source_config.get("enabled", True):
            continue
        if source_ids and source_config["id"] not in source_ids:
            continue
        if not source_config.get("requires_adjustment", False):
            continue
        statuses.append(GenericPageSource(source_config).source_status(context))
    return statuses


def run_sources(
    sources: list[BaseSource],
    context: SourceContext,
    max_workers: int = 6,
    entity_profile: dict[str, object] | None = None,
) -> RunResult:
    started = datetime.now().astimezone().isoformat(timespec="seconds")
    result = RunResult(started_at=started)
    result.sources_checked = [source.name for source in sources]
    result.source_statuses = [source.source_status(context) for source in sources]

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(max_workers, 12))) as executor:
        futures = {executor.submit(source.collect, context): source for source in sources}
        for future in concurrent.futures.as_completed(futures):
            source = futures[future]
            try:
                opportunities = future.result()
            except Exception as exc:
                result.incidents.append(
                    Incident(
                        source_id=source.id,
                        source_name=source.name,
                        message=f"{type(exc).__name__}: {exc}",
                        checked_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                    )
                )
                continue
            result.sources_succeeded.append(source.name)
            result.opportunities.extend(opportunities)
            for message in getattr(source, "errors", []):
                result.incidents.append(
                    Incident(
                        source_id=source.id,
                        source_name=source.name,
                        message=message,
                        checked_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                    )
                )

    for opportunity in result.opportunities:
        apply_caribdis_scoring(
            opportunity,
            today=context.today,
            entity_profile=entity_profile,
        )
    result.finished_at = datetime.now().astimezone().isoformat(timespec="seconds")
    return result


def run_search(
    config: dict[str, Any],
    start_date: date,
    end_date: date,
    root: Path,
    source_ids: set[str] | None = None,
    include_experimental: bool = False,
) -> RunResult:
    cache_dir = root / config.get("cache_directory", "informes_caribdis/cache")
    context = SourceContext(
        start_date=start_date,
        end_date=end_date,
        today=date.today(),
        timeout=int(config.get("request_timeout_seconds", 20)),
        cache_dir=cache_dir,
    )
    sources = create_sources(
        config,
        source_ids=source_ids,
        include_experimental=include_experimental,
    )
    result = run_sources(
        sources,
        context,
        max_workers=int(config.get("max_workers", 6)),
        entity_profile=config.get("entity_profile"),
    )
    result.pending_sources = pending_source_statuses(
        config,
        context,
        source_ids=source_ids,
        include_experimental=include_experimental,
    )
    return result
