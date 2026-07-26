import tempfile
import unittest
from datetime import date
from pathlib import Path

from caribdis_search.models import Opportunity
from caribdis_search.runner import run_sources
from caribdis_search.sources.base import BaseSource, SourceContext


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


if __name__ == "__main__":
    unittest.main()
