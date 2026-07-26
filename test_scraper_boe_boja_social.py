import csv
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import scraper_boe_boja_social as scraper


def notice(title: str, source: str = "BOJA") -> scraper.Notice:
    return scraper.Notice(
        source=source,
        title=title,
        url="https://www.juntadeandalucia.es/boja/2026/1/1.html",
        published_date="2026-07-26",
        entity="Junta de Andalucía",
        section="Subvenciones",
        topic="",
        summary="",
    )


class CaribdisScoringTests(unittest.TestCase):
    def test_marine_andalusian_grant_is_high_and_direct(self) -> None:
        assessment = scraper.score_caribdis(
            notice(
                "Convocatoria de subvenciones para conservación marina y "
                "biodiversidad marina en Andalucía"
            ),
            "Podrán participar entidades sin ánimo de lucro.",
        )

        self.assertGreaterEqual(assessment.score, 75)
        self.assertEqual(assessment.priority, "Alta")
        self.assertEqual(assessment.fit, "Directa")
        self.assertEqual(assessment.category, "Conservación y biodiversidad marina")
        self.assertIn("conservación marina", assessment.keywords)

    def test_social_education_grant_detects_caribdis_terms(self) -> None:
        assessment = scraper.score_caribdis(
            notice(
                "Ayudas para educación ambiental con menores vulnerables, "
                "alumnado NEAE y discapacidad en Sevilla"
            ),
            "Convocatoria dirigida a asociaciones.",
        )

        self.assertGreaterEqual(assessment.score, 50)
        self.assertIn(assessment.priority, {"Alta", "Media"})
        self.assertEqual(assessment.fit, "Directa")
        self.assertIn("NEAE", assessment.keywords)
        self.assertIn("discapacidad", assessment.keywords)

    def test_restricted_beneficiary_requires_partner(self) -> None:
        assessment = scraper.score_caribdis(
            notice("Subvenciones para conservación marina exclusivamente para universidades"),
            "Actuaciones de biodiversidad marina y ciencia ciudadana en Andalucía.",
        )

        self.assertEqual(assessment.priority, "Baja")
        self.assertEqual(assessment.fit, "Solo con socio")
        self.assertLessEqual(assessment.score, 49)

    def test_direct_named_award_is_discarded(self) -> None:
        assessment = scraper.score_caribdis(
            notice("Concesión directa a la Fundación X para conservación marina en Andalucía"),
            "",
        )

        self.assertEqual(assessment.priority, "Descartar")
        self.assertEqual(assessment.fit, "No válida")
        self.assertIn("concesión directa", assessment.reason)

    def test_regulatory_basis_is_marked_for_monitoring(self) -> None:
        assessment = scraper.score_caribdis(
            notice("Bases reguladoras de ayudas para biodiversidad marina en Andalucía"),
            "Entidades sin ánimo de lucro dedicadas al medio marino.",
        )

        self.assertGreaterEqual(assessment.score, 25)
        self.assertEqual(assessment.fit, "Vigilar próxima edición")


class CaribdisOutputTests(unittest.TestCase):
    def sample_grant(self) -> scraper.SocialGrant:
        return scraper.SocialGrant(
            source="BOJA",
            entity="Junta de Andalucía",
            scope="Andalucía",
            title="Ayudas para conservación marina en Andalucía",
            published_date="2026-07-26",
            open_date="2026-07-26",
            close_date="2026-09-30",
            url="https://www.juntadeandalucia.es/boja/2026/1/1.html",
            pdf_url="",
            beneficiary_hint="Entidades sin ánimo de lucro.",
            matched_terms=["subvenciones", "entidades sin ánimo de lucro"],
            score=12,
            caribdis_score=82,
            caribdis_priority="Alta",
            caribdis_fit="Directa",
            caribdis_reason="Encaje directo en conservación marina.",
            caribdis_category="Conservación y biodiversidad marina",
            caribdis_keywords=["conservación marina", "Andalucía"],
            checked_at="2026-07-26T10:00:00+02:00",
        )

    def test_outputs_are_created_and_txt_is_appended(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory)
            txt = output / scraper.CUMULATIVE_TXT_FILENAME
            txt.write_text("CONTENIDO HISTORICO\n", encoding="utf-8")

            scraper.write_outputs(
                output,
                [date(2026, 7, 26)],
                [self.sample_grant()],
                [],
            )

            txt_content = txt.read_text(encoding="utf-8")
            self.assertTrue(txt_content.startswith("CONTENIDO HISTORICO\n"))
            self.assertIn("Puntuacion CARIBDIS: 82/100", txt_content)
            self.assertIn("Encaje CARIBDIS: Directa", txt_content)

            ranking = output / scraper.CARIBDIS_RANKING_FILENAME
            json_path = output / scraper.CARIBDIS_JSON_FILENAME
            csv_path = output / scraper.CARIBDIS_CSV_FILENAME
            self.assertTrue(ranking.exists())
            self.assertTrue(json_path.exists())
            self.assertTrue(csv_path.exists())

            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload[0]["caribdis_score"], 82)
            self.assertEqual(payload[0]["caribdis_fit"], "Directa")

            with csv_path.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["caribdis_priority"], "Alta")
            self.assertEqual(rows[0]["caribdis_keywords"], "conservación marina; Andalucía")


if __name__ == "__main__":
    unittest.main()
