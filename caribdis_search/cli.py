from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

from .config import load_configuration
from .history import (
    apply_recurrence,
    deduplicate,
    load_history,
    save_current_data,
    save_history,
    update_history,
)
from .report import write_report
from .runner import run_search
from .scoring import apply_caribdis_scoring


ROOT = Path(__file__).resolve().parents[1]


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Buscador global de ayudas para CARIBDIS")
    parser.add_argument("--config-dir", type=Path, default=ROOT / "config")
    parser.add_argument("--date", type=parse_date, help="Fecha final en formato YYYY-MM-DD.")
    parser.add_argument("--start-date", type=parse_date, help="Fecha inicial en formato YYYY-MM-DD.")
    parser.add_argument("--end-date", type=parse_date, help="Fecha final en formato YYYY-MM-DD.")
    parser.add_argument("--days", type=int, default=10, help="Días hacia atrás, incluyendo la fecha final.")
    parser.add_argument(
        "--historical",
        action="store_true",
        help="Revisión histórica de 365 días si no se indica fecha inicial.",
    )
    parser.add_argument(
        "--source-id",
        action="append",
        default=[],
        help="Limita la ejecución a una fuente; puede repetirse.",
    )
    return parser.parse_args()


def resolve_period(args: argparse.Namespace) -> tuple[date, date]:
    end_date = args.end_date or args.date or date.today()
    if args.start_date:
        start_date = args.start_date
    else:
        days = 365 if args.historical else max(1, args.days)
        start_date = end_date - timedelta(days=days - 1)
    if start_date > end_date:
        raise ValueError("La fecha inicial no puede ser posterior a la fecha final")
    return start_date, end_date


def write_run_log(path: Path, run_data: dict[str, object]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S")
    (path / f"ejecucion_{timestamp}.json").write_text(
        json.dumps(run_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    start_date, end_date = resolve_period(args)
    config = load_configuration(args.config_dir)
    source_ids = set(args.source_id) or None
    run = run_search(config, start_date, end_date, ROOT, source_ids=source_ids)

    history_path = ROOT / config["history_path"]
    data_path = ROOT / config["data_path"]
    report_path = ROOT / config["report_path"]
    checked_at = datetime.now().astimezone().isoformat(timespec="seconds")
    history = load_history(history_path)
    opportunities = deduplicate(run.opportunities)
    apply_recurrence(opportunities, history)
    for opportunity in opportunities:
        apply_caribdis_scoring(opportunity, today=date.today())
    history = update_history(opportunities, history, checked_at)
    save_history(history_path, history)
    save_current_data(data_path, opportunities)
    run.opportunities = opportunities
    write_report(report_path, run, start_date, end_date)
    write_run_log(
        ROOT / config["log_directory"],
        {
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "sources_checked": run.sources_checked,
            "sources_succeeded": run.sources_succeeded,
            "incidents": [incident.to_dict() for incident in run.incidents],
            "opportunities": len(opportunities),
            "report": str(report_path),
        },
    )
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        summary_lines = [
            "# Revisión global de ayudas CARIBDIS",
            "",
            f"- Periodo: {start_date.isoformat()} a {end_date.isoformat()}",
            f"- Oportunidades únicas: {len(opportunities)}",
            f"- Fuentes correctas: {len(run.sources_succeeded)}/{len(run.sources_checked)}",
            f"- Incidencias: {len(run.incidents)}",
            f"- Informe: `{config['report_path']}`",
            "",
        ]
        if run.incidents:
            summary_lines.extend(["## Fuentes con incidencias", ""])
            summary_lines.extend(
                f"- {incident.source_name}: {incident.message}" for incident in run.incidents
            )
        Path(summary_path).write_text("\n".join(summary_lines).rstrip() + "\n", encoding="utf-8")

    print(
        f"Buscador CARIBDIS: {len(opportunities)} oportunidades, "
        f"{len(run.incidents)} incidencias, {len(run.sources_succeeded)}/"
        f"{len(run.sources_checked)} fuentes correctas. Informe: {report_path}"
    )
    return 0 if run.sources_succeeded or not run.sources_checked else 1
