import tempfile
import unittest
from datetime import date
from pathlib import Path

from caribdis_search.models import Opportunity, RunResult
from caribdis_search.report import ranked_opportunities, write_report


def item(
    title: str,
    status: str,
    score: int,
    close_date: str,
    participation: str = "Solicitud directa",
) -> Opportunity:
    return Opportunity(
        title=title,
        status=status,
        caribdis_score=score,
        priority="Alta",
        close_date=close_date,
        participation=participation,
        official_url=f"https://example.org/{title.lower()}",
    )


class ReportTests(unittest.TestCase):
    def test_ranking_prioritizes_open_status_before_score(self) -> None:
        opportunities = [
            item("Próxima", "Próxima", 99, "2026-08-01"),
            item("Abierta media", "Abierta", 60, "2026-09-01"),
            item("Abierta alta", "Abierta", 90, "2026-10-01"),
        ]

        ranked = ranked_opportunities(opportunities, today=date(2026, 7, 26))

        self.assertEqual([entry.title for entry in ranked], ["Abierta alta", "Abierta media", "Próxima"])

    def test_report_contains_all_sections_and_overwrites_file(self) -> None:
        run = RunResult(
            opportunities=[item("Ayuda marina", "Abierta", 90, "2026-09-30")],
            sources_checked=["boe"],
            sources_succeeded=["boe"],
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "INFORME_UNICO_AYUDAS_CARIBDIS.md"
            path.write_text("contenido anterior", encoding="utf-8")

            write_report(
                path,
                run,
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 26),
                today=date(2026, 7, 26),
            )

            content = path.read_text(encoding="utf-8")
            self.assertNotIn("contenido anterior", content)
            self.assertIn("## 3. Top 10 ayudas abiertas para solicitar ahora", content)
            self.assertIn("## 17. Ayudas descartadas y motivo", content)
            self.assertIn("## 19. Ranking general completo", content)
            self.assertIn("## 20. Recomendaciones de actuación inmediata", content)
            self.assertIn("### 1. Ayuda marina", content)


if __name__ == "__main__":
    unittest.main()
