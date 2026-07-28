import tempfile
import unittest
from datetime import date
from pathlib import Path

from caribdis_search.models import Opportunity, RunResult
from caribdis_search.report import ranked_opportunities, render_report, write_report


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

    def test_ranking_places_partner_calls_after_upcoming_direct_calls(self) -> None:
        high = item("Abierta alta", "Abierta", 90, "2026-10-01")
        medium = item("Abierta media", "Abierta", 60, "2026-09-01")
        medium.priority = "Media"
        upcoming = item(
            "Próxima directa",
            "Próxima",
            80,
            "2026-11-01",
            participation="Vigilar próxima edición",
        )
        partner = item(
            "Abierta con consorcio",
            "Abierta",
            95,
            "2026-08-01",
            participation="Socia de consorcio europeo",
        )

        ranked = ranked_opportunities(
            [partner, upcoming, medium, high],
            today=date(2026, 7, 26),
        )

        self.assertEqual(
            [entry.title for entry in ranked],
            ["Abierta alta", "Abierta media", "Próxima directa", "Abierta con consorcio"],
        )

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

    def test_discarded_items_do_not_appear_in_open_top(self) -> None:
        valid = item("Ayuda válida", "Abierta", 70, "2026-09-30")
        discarded = item("Ayuda descartada", "Abierta", 0, "2026-08-01")
        discarded.priority = "Descartar"
        run = RunResult(opportunities=[valid, discarded])

        content = render_report(
            run,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 26),
            today=date(2026, 7, 26),
        )
        top_section = content.split(
            "## 3. Top 10 ayudas abiertas para solicitar ahora", 1
        )[1].split("## 4.", 1)[0]

        self.assertIn("Ayuda válida", top_section)
        self.assertNotIn("Ayuda descartada", top_section)
        self.assertIn("Ayuda descartada", content.split("## 17.", 1)[1])

    def test_discarded_items_appear_only_in_section_17(self) -> None:
        valid = item("FECYT Cultura Científica", "Abierta", 80, "2026-09-16")
        discarded = item("Premios AEPD", "Abierta", 0, "2026-08-01")
        discarded.priority = "Descartar"
        discarded.risks = ["premio de la AEPD sin encaje operativo CARIBDIS"]

        content = render_report(
            RunResult(opportunities=[valid, discarded]),
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 26),
            today=date(2026, 7, 26),
        )
        before_discarded = content.split("## 17. Ayudas descartadas y motivo", 1)[0]
        discarded_section = content.split(
            "## 17. Ayudas descartadas y motivo", 1
        )[1].split("## 18.", 1)[0]
        after_discarded = content.split("## 18.", 1)[1]

        self.assertNotIn("Premios AEPD", before_discarded)
        self.assertIn("Premios AEPD", discarded_section)
        self.assertNotIn("Premios AEPD", after_discarded)

    def test_low_without_thematic_fit_does_not_enter_top_10(self) -> None:
        low = item("Infancia genérica", "Abierta", 49, "2026-09-30")
        low.priority = "Baja"
        low.thematic_minimum_met = False

        content = render_report(
            RunResult(opportunities=[low]),
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 26),
            today=date(2026, 7, 26),
        )
        top_section = content.split("## 3.", 1)[1].split("## 4.", 1)[0]

        self.assertNotIn("Infancia genérica", top_section)

    def test_strategic_procedure_has_separate_non_financial_section(self) -> None:
        strategic = item(
            "Inscripción de entidad colaboradora",
            "Abierta",
            0,
            "Dato no localizado",
        )
        strategic.priority = "Descartar"
        strategic.strategic_procedure = True
        strategic.financial_opportunity = False
        strategic.procedure_code = "15802"
        strategic.beneficiaries = "Asociaciones y organizaciones"
        strategic.new_association_eligibility = "No aplica como ayuda económica."

        content = render_report(
            RunResult(opportunities=[strategic]),
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 26),
            today=date(2026, 7, 26),
        )
        discarded_section = content.split(
            "## 17. Ayudas descartadas y motivo", 1
        )[1].split("## Trámites estratégicos", 1)[0]
        strategic_section = content.split(
            "## Trámites estratégicos para fortalecer CARIBDIS", 1
        )[1].split("## 18.", 1)[0]

        self.assertNotIn(strategic.title, discarded_section)
        self.assertIn(strategic.title, strategic_section)


if __name__ == "__main__":
    unittest.main()
