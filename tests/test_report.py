import tempfile
import unittest
from datetime import date
from pathlib import Path

from caribdis_search.models import Opportunity, RunResult, ScoringBreakdown
from caribdis_search.report import ranked_opportunities, render_report, write_report


def item(
    title: str,
    status: str,
    score: int,
    close_date: str,
    participation: str = "Solicitud directa",
) -> Opportunity:
    if score >= 85:
        priority = "Muy alta"
    elif score >= 70:
        priority = "Alta"
    elif score >= 50:
        priority = "Media"
    elif score >= 25:
        priority = "Baja"
    else:
        priority = "Descartar"
    return Opportunity(
        title=title,
        status=status,
        caribdis_score=score,
        priority=priority,
        close_date=close_date,
        participation=participation,
        official_url=f"https://example.org/{title.lower()}",
        funding_instrument="Subvención",
        funding_percentage=70,
        cofinancing_percentage=30,
        advance_percentage=40,
        cashflow_risk="Medio",
        suitable_for_new_entity=True,
        thematic_minimum_met=True,
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

    def test_ranking_places_all_open_calls_before_upcoming_calls(self) -> None:
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
            ["Abierta alta", "Abierta media", "Abierta con consorcio", "Próxima directa"],
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
            headings = [
                "## 1. Resumen ejecutivo",
                "## 2. Ayudas abiertas que CARIBDIS puede solicitar directamente",
                "## 3. Ayudas prioritarias para una asociación nueva",
                "## 4. Ayudas para sostener la asociación",
                "## 5. Ayudas para proyectos marinos y científicos",
                "## 6. Ayudas para infancia, juventud, discapacidad, NEAE e inclusión",
                "## 7. Ayudas de la Junta de Andalucía",
                "## 8. Ayudas de diputaciones y ayuntamientos",
                "## 9. Ayudas estatales y BDNS",
                "## 10. Ayudas europeas",
                "## 11. Donaciones, patrocinios y fundaciones privadas",
                "## 12. Ayudas que exigen socio",
                "## 13. Ayudas para las que CARIBDIS todavía no cumple requisitos",
                "## 14. Requisitos que deben prepararse",
                "## 15. Trámites estratégicos para fortalecer CARIBDIS",
                "## 16. Ayudas descartadas y motivo",
                "## 17. Calendario de próximos 3, 6 y 12 meses",
                "## 18. Ranking general",
                "## 19. Recomendaciones de actuación inmediata",
            ]
            for heading in headings:
                self.assertIn(heading, content)
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
            "## 2. Ayudas abiertas que CARIBDIS puede solicitar directamente", 1
        )[1].split("## 3.", 1)[0]

        self.assertIn("Ayuda válida", top_section)
        self.assertNotIn("Ayuda descartada", top_section)
        self.assertIn("Ayuda descartada", content.split("## 16.", 1)[1])

    def test_discarded_items_appear_only_in_section_16(self) -> None:
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
        before_discarded = content.split("## 16. Ayudas descartadas y motivo", 1)[0]
        discarded_section = content.split(
            "## 16. Ayudas descartadas y motivo", 1
        )[1].split("## 17.", 1)[0]
        after_discarded = content.split("## 17.", 1)[1]

        self.assertNotIn("Premios AEPD", before_discarded)
        self.assertIn("Premios AEPD", discarded_section)
        self.assertNotIn("Premios AEPD", after_discarded)

    def test_low_without_thematic_fit_does_not_enter_top_10(self) -> None:
        high = item("FECYT Cultura Científica", "Abierta", 80, "2026-09-16")
        lows = []
        for index in range(1, 11):
            low = item(
                f"Infancia genérica {index}",
                "Abierta",
                49,
                "2026-09-30",
            )
            low.priority = "Baja"
            low.thematic_minimum_met = False
            lows.append(low)

        content = render_report(
            RunResult(opportunities=[*lows, high]),
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 26),
            today=date(2026, 7, 26),
        )
        top_section = content.split("## 3.", 1)[1].split("## 4.", 1)[0]
        ranking_section = content.split("## 18. Ranking general", 1)[1].split(
            "## 19.",
            1,
        )[0]

        self.assertNotIn("Infancia genérica", top_section)
        self.assertIn("### 1. FECYT Cultura Científica", ranking_section)
        self.assertNotIn("### 2. Infancia genérica", ranking_section)
        self.assertIn("### 11. Infancia genérica", ranking_section)
        self.assertIn(
            "Otras oportunidades de prioridad Baja fuera del Top CARIBDIS",
            ranking_section,
        )

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
            "## 16. Ayudas descartadas y motivo", 1
        )[1].split("## 17.", 1)[0]
        strategic_section = content.split(
            "## 15. Trámites estratégicos para fortalecer CARIBDIS", 1
        )[1].split("## 16.", 1)[0]

        self.assertNotIn(strategic.title, discarded_section)
        self.assertIn(strategic.title, strategic_section)

    def test_report_shows_financial_viability_and_cashflow_risk(self) -> None:
        opportunity = item("Ayuda de funcionamiento", "Abierta", 80, "2026-09-30")
        opportunity.funding_instrument = "Subvención"
        opportunity.funding_percentage = 70
        opportunity.advance_percentage = 40
        opportunity.cashflow_risk = "Medio"
        opportunity.financial_viability_reason = "Financiación del 70 % y anticipo del 40 %."
        opportunity.operating_costs_eligible = True

        content = render_report(
            RunResult(opportunities=[opportunity]),
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 26),
            today=date(2026, 7, 26),
        )

        self.assertIn("Riesgo de tesorería", content)
        self.assertIn("Porcentaje financiado: 70 %", content)
        self.assertIn("Gastos de funcionamiento: Sí", content)
        self.assertIn("Apta para entidad nueva: Sí", content)

    def test_summary_contains_new_nonprofit_financial_message(self) -> None:
        content = render_report(
            RunResult(opportunities=[]),
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 26),
            today=date(2026, 7, 26),
        )

        self.assertIn(
            "CARIBDIS es una asociación andaluza sin ánimo de lucro de nueva creación",
            content,
        )
        self.assertIn("financiación a fondo perdido", content)
        self.assertIn("cobertura de gastos de funcionamiento", content)
        for counter in [
            "Oportunidades totales",
            "Solicitud directa",
            "Con socio",
            "Aptas para entidad nueva",
            "No aptas por antigüedad",
            "Financiación del 100 %",
            "Con anticipo",
            "Riesgo de tesorería alto o muy alto",
            "Trámites estratégicos",
            "Descartadas",
        ]:
            self.assertIn(counter, content)

    def test_sustaining_and_private_funding_have_separate_sections(self) -> None:
        operating = item(
            "Ayuda para seguros y gestoría",
            "Abierta",
            80,
            "2026-09-30",
        )
        operating.operating_costs_eligible = True
        operating.insurance_eligible = True
        donation = item("Donación marina", "Abierta", 75, "2026-10-15")
        donation.funding_instrument = "Donación"
        donation.source_group = "Fundaciones privadas"

        content = render_report(
            RunResult(opportunities=[operating, donation]),
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 26),
            today=date(2026, 7, 26),
        )
        sustaining = content.split(
            "## 4. Ayudas para sostener la asociación", 1
        )[1].split("## 5.", 1)[0]
        private = content.split(
            "## 11. Donaciones, patrocinios y fundaciones privadas", 1
        )[1].split("## 12.", 1)[0]

        self.assertIn(operating.title, sustaining)
        self.assertIn(donation.title, private)

    def test_ranking_prefers_fit_over_amount(self) -> None:
        strong_fit = item("Encaje marino", "Abierta", 80, "2026-09-30")
        strong_fit.scoring = ScoringBreakdown(
            thematic_fit=25,
            social_educational_fit=5,
        )
        strong_fit.max_amount = "10.000 EUR"
        large_generic = item("Importe elevado", "Abierta", 80, "2026-09-30")
        large_generic.scoring = ScoringBreakdown(thematic_fit=5)
        large_generic.max_amount = "2.000.000 EUR"

        ranked = ranked_opportunities(
            [large_generic, strong_fit],
            today=date(2026, 7, 26),
        )

        self.assertEqual(ranked[0].title, "Encaje marino")

    def test_open_direct_new_entity_is_ranked_first(self) -> None:
        direct_new = item("Directa nueva", "Abierta", 75, "2026-10-30")
        partner_high = item(
            "Con socio",
            "Abierta",
            95,
            "2026-08-30",
            participation="Socia de consorcio europeo",
        )
        partner_high.suitable_for_new_entity = False
        upcoming = item("Próxima", "Próxima", 99, "2026-08-01")

        ranked = ranked_opportunities(
            [partner_high, upcoming, direct_new],
            today=date(2026, 7, 26),
        )

        self.assertEqual(
            [entry.title for entry in ranked],
            ["Directa nueva", "Con socio", "Próxima"],
        )

    def test_repository_has_one_main_markdown_report(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        reports = sorted(
            path.name
            for path in (repository_root / "informes_caribdis").glob("*.md")
        )

        self.assertEqual(reports, ["INFORME_UNICO_AYUDAS_CARIBDIS.md"])


if __name__ == "__main__":
    unittest.main()
