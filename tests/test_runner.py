import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from caribdis_search.cli import write_run_log
from caribdis_search.config import load_configuration
from caribdis_search.models import Opportunity
from caribdis_search.runner import create_sources, pending_source_statuses, run_sources
from caribdis_search.scoring import apply_caribdis_scoring
from caribdis_search.sources.base import BaseSource, SourceContext
from caribdis_search.sources.verified import VerifiedMetadataSource


class GoodSource(BaseSource):
    def __init__(self) -> None:
        super().__init__(
            {
                "id": "good",
                "name": "Fuente correcta",
                "url": "https://example.org",
                "official_domains": ["example.org"],
            }
        )

    def collect(self, context: SourceContext) -> list[Opportunity]:
        return [
            Opportunity(
                title="Subvención para biodiversidad marina en Andalucía",
                beneficiaries="Asociaciones sin ánimo de lucro",
                territory="Andalucía",
                status="Abierta",
                official_url="https://example.org/call",
            )
        ]


class FailingSource(BaseSource):
    def __init__(self) -> None:
        super().__init__(
            {
                "id": "bad",
                "name": "Fuente fallida",
                "url": "https://invalid.example",
                "official_domains": ["invalid.example"],
            }
        )

    def collect(self, context: SourceContext) -> list[Opportunity]:
        raise TimeoutError("timeout de prueba")


class RunnerTests(unittest.TestCase):
    def test_one_source_failure_does_not_stop_other_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            context = SourceContext(
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 26),
                today=date(2026, 7, 26),
                timeout=1,
                cache_dir=Path(temporary_directory),
            )

            result = run_sources([FailingSource(), GoodSource()], context, max_workers=2)

        self.assertEqual(len(result.opportunities), 1)
        self.assertEqual(result.sources_succeeded, ["Fuente correcta"])
        self.assertEqual(len(result.incidents), 1)
        self.assertIn("TimeoutError", result.incidents[0].message)

    def test_sources_requiring_adjustment_are_disabled_by_default(self) -> None:
        config = {
            "legacy_boe_boja_enabled": False,
            "sources": [
                {
                    "id": "dynamic",
                    "name": "Portal dinámico",
                    "group": "Unión Europea",
                    "adapter": "html",
                    "url": "https://example.org",
                    "official_domains": ["example.org"],
                    "coverage_type": "landing",
                    "requires_adjustment": True,
                    "adjustment_reason": "Requiere API.",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            context = SourceContext(
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 26),
                today=date(2026, 7, 26),
                timeout=1,
                cache_dir=Path(temporary_directory),
            )
            pending = pending_source_statuses(config, context)

        self.assertEqual(create_sources(config), [])
        self.assertEqual(len(create_sources(config, include_experimental=True)), 1)
        self.assertEqual([status.source_id for status in pending], ["dynamic"])

    @patch("caribdis_search.sources.verified.fetch_text")
    def test_fecyt_verified_call_is_direct_and_high(self, fetch_text_mock) -> None:
        fetch_text_mock.return_value = (
            "Convocatoria 2026 FECYT. Cultura científica, divulgación científica "
            "y ciencia ciudadana."
        )
        root = Path(__file__).resolve().parents[1]
        config = load_configuration(root / "config")
        fecyt_config = next(source for source in config["sources"] if source["id"] == "fecyt")
        source = VerifiedMetadataSource(fecyt_config)
        with tempfile.TemporaryDirectory() as temporary_directory:
            context = SourceContext(
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 27),
                today=date(2026, 7, 27),
                timeout=1,
                cache_dir=Path(temporary_directory),
            )
            item = source.collect(context)[0]
        apply_caribdis_scoring(item, today=context.today)

        self.assertEqual(item.status, "Abierta")
        self.assertEqual(item.participation, "Solicitud directa")
        self.assertIn(item.priority, {"Muy alta", "Alta"})
        self.assertTrue(item.metadata_verified)
        self.assertEqual(item.close_date, "2026-09-16")
        self.assertEqual(item.funding_instrument, "Subvención")
        self.assertEqual(item.funding_percentage, 70)
        self.assertEqual(item.advance_percentage, 60)
        self.assertTrue(item.suitable_for_new_entity)
        self.assertNotIn("Ayuda para personal", item.funding_purposes)

    @patch("caribdis_search.sources.verified.fetch_text", return_value="Página de error")
    def test_verified_source_rejects_unexpected_official_page(self, fetch_text_mock) -> None:
        del fetch_text_mock
        root = Path(__file__).resolve().parents[1]
        config = load_configuration(root / "config")
        fecyt_config = next(source for source in config["sources"] if source["id"] == "fecyt")
        source = VerifiedMetadataSource(fecyt_config)
        with tempfile.TemporaryDirectory() as temporary_directory:
            context = SourceContext(
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 27),
                today=date(2026, 7, 27),
                timeout=1,
                cache_dir=Path(temporary_directory),
            )
            with self.assertRaisesRegex(RuntimeError, "marcas de verificación"):
                source.collect(context)

    def test_run_log_uses_single_latest_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory)
            write_run_log(path, {"run": 1})
            write_run_log(path, {"run": 2})

            self.assertEqual([entry.name for entry in path.iterdir()], ["ultima_ejecucion.json"])
            self.assertIn('"run": 2', (path / "ultima_ejecucion.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
