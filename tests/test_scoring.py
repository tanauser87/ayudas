import unittest

from caribdis_search.models import Opportunity
from caribdis_search.scoring import apply_caribdis_scoring


def opportunity(title: str, beneficiaries: str, status: str = "Abierta") -> Opportunity:
    return Opportunity(
        title=title,
        organization="Organismo convocante",
        source="Fuente oficial",
        source_group="Junta de Andalucía",
        organization_type="Administración autonómica",
        territory="Andalucía",
        status=status,
        beneficiaries=beneficiaries,
        official_url="https://www.juntadeandalucia.es/convocatoria",
        summary="Subvención a fondo perdido para proyectos.",
    )


class ScoringTests(unittest.TestCase):
    def test_marine_conservation_is_very_high(self) -> None:
        item = opportunity(
            "Conservación de fauna submarina, biodiversidad marina y hábitats marinos",
            "Asociaciones sin ánimo de lucro.",
        )

        apply_caribdis_scoring(item)

        self.assertGreaterEqual(item.caribdis_score, 85)
        self.assertEqual(item.priority, "Muy alta")
        self.assertEqual(item.participation, "Solicitud directa")
        self.assertEqual(item.main_theme, "Conservación y biodiversidad marina")

    def test_citizen_science_and_workshops_score_high(self) -> None:
        item = opportunity(
            "Ciencia ciudadana, educación ambiental y talleres científicos",
            "Asociaciones sin ánimo de lucro que trabajen con menores, alumnado NEAE "
            "y juventud en situación de vulnerabilidad social.",
        )

        apply_caribdis_scoring(item)

        self.assertGreaterEqual(item.caribdis_score, 70)
        self.assertIn(item.priority, {"Muy alta", "Alta"})
        self.assertIn("ciencia ciudadana", item.caribdis_keywords)
        self.assertIn("neae", item.caribdis_keywords)

    def test_university_only_requires_scientific_partner(self) -> None:
        item = opportunity(
            "Subvenciones para biodiversidad marina y ciencia ciudadana",
            "Podrán solicitarlas exclusivamente universidades y centros de investigación.",
        )

        apply_caribdis_scoring(item)

        self.assertEqual(item.participation, "Socia de universidad o centro científico")
        self.assertEqual(item.scoring.eligibility, 15)

    def test_municipality_only_requires_municipal_partner(self) -> None:
        item = opportunity(
            "Ayudas a proyectos de educación ambiental en playas",
            "Convocatoria exclusivamente para ayuntamientos.",
        )

        apply_caribdis_scoring(item)

        self.assertEqual(item.participation, "Socia de ayuntamiento")
        self.assertEqual(item.scoring.eligibility, 15)

    def test_direct_named_grant_is_discarded(self) -> None:
        item = opportunity(
            "Concesión directa a la Fundación Ejemplo para conservación marina",
            "La Fundación Ejemplo es la beneficiaria única.",
        )

        apply_caribdis_scoring(item)

        self.assertEqual(item.caribdis_score, 0)
        self.assertEqual(item.priority, "Descartar")
        self.assertEqual(item.participation, "No elegible")

    def test_european_consortium_is_classified_as_partner(self) -> None:
        item = opportunity(
            "Horizon Europe para biodiversidad marina y restauración del océano",
            "Consorcio europeo internacional requerido.",
        )
        item.territory = "Unión Europea - España elegible"

        apply_caribdis_scoring(item)

        self.assertEqual(item.participation, "Socia de consorcio europeo")
        self.assertEqual(item.scoring.eligibility, 15)

    def test_exclusive_other_region_is_not_eligible(self) -> None:
        item = opportunity(
            "Convocatoria Social Castilla-La Mancha",
            "Entidades privadas sin ánimo de lucro.",
        )
        item.territory = "España"

        apply_caribdis_scoring(item)

        self.assertEqual(item.caribdis_score, 0)
        self.assertEqual(item.priority, "Descartar")
        self.assertEqual(item.participation, "No elegible")

    def test_nominative_grant_is_discarded(self) -> None:
        item = opportunity(
            "Subvención nominativa Museo Ejemplo 2026",
            "Entidad beneficiaria identificada.",
        )

        apply_caribdis_scoring(item)

        self.assertEqual(item.caribdis_score, 0)
        self.assertEqual(item.participation, "No elegible")

    def test_personal_scholarship_is_discarded(self) -> None:
        item = opportunity(
            "Convocatoria de dos becas de colaboración para estudiantes",
            "Personas físicas matriculadas.",
        )

        apply_caribdis_scoring(item)

        self.assertEqual(item.caribdis_score, 0)
        self.assertEqual(item.priority, "Descartar")

    def test_non_competitive_direct_grant_is_discarded(self) -> None:
        item = opportunity(
            "Concesión directa de subvenciones a diversas entidades sociales",
            "Entidades sin ánimo de lucro.",
        )

        apply_caribdis_scoring(item)

        self.assertEqual(item.caribdis_score, 0)
        self.assertIn("concesión directa no competitiva", item.risks)

    def test_foreign_trade_grant_is_discarded(self) -> None:
        item = opportunity(
            "Ayudas de ICEX España Exportación e Inversiones",
            "Asociaciones sin ánimo de lucro.",
        )

        apply_caribdis_scoring(item)

        self.assertEqual(item.priority, "Descartar")
        self.assertEqual(item.participation, "No elegible")


if __name__ == "__main__":
    unittest.main()
