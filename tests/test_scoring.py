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
        item.suitable_for_new_entity = False
        item.recurrent = True

        apply_caribdis_scoring(item)

        self.assertEqual(item.caribdis_score, 0)
        self.assertEqual(item.priority, "Descartar")
        self.assertEqual(item.participation, "No elegible")

    def test_personal_scholarship_is_discarded(self) -> None:
        item = opportunity(
            "Convocatoria de dos becas de colaboración para estudiantes",
            "Personas físicas matriculadas.",
        )

        apply_caribdis_scoring(item)

        self.assertEqual(item.caribdis_score, 0)
        self.assertEqual(item.priority, "Descartar")

    def test_collaboration_scholarship_title_is_discarded(self) -> None:
        item = opportunity(
            "Becas de Colaboración en Departamentos Universitarios",
            "Estudiantes universitarios.",
        )

        apply_caribdis_scoring(item)

        self.assertEqual(item.caribdis_score, 0)
        self.assertEqual(item.priority, "Descartar")
        self.assertIn("beca personal", item.risks)

    def test_postdoctoral_research_contracts_are_discarded(self) -> None:
        item = opportunity(
            "Convocatoria de 30 contratos de investigadores postdoctorales",
            "Universidades y centros de investigación.",
        )

        apply_caribdis_scoring(item)

        self.assertEqual(item.caribdis_score, 0)
        self.assertEqual(item.priority, "Descartar")
        self.assertIn("investigación doctoral o postdoctoral", item.risks)

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

    def test_generic_social_fit_does_not_pass_thematic_threshold(self) -> None:
        item = opportunity(
            "Programa de responsabilidad social para infancia y vulnerabilidad",
            "Asociaciones sin ánimo de lucro que realizan educación genérica.",
        )

        apply_caribdis_scoring(item)

        self.assertFalse(item.thematic_minimum_met)
        self.assertIn(item.priority, {"Baja", "Descartar"})
        self.assertLess(item.caribdis_score, 50)

    def test_aepd_prize_is_discarded(self) -> None:
        item = opportunity(
            "Premios de la Agencia Española de Protección de Datos",
            "Asociaciones y entidades que trabajen con menores.",
        )

        apply_caribdis_scoring(item)

        self.assertEqual(item.priority, "Descartar")
        self.assertIn("premio de la AEPD", " ".join(item.risks))


class FinancialScoringTests(unittest.TestCase):
    def financial_opportunity(self) -> Opportunity:
        item = opportunity(
            "Ayuda para biodiversidad marina y educación ambiental",
            "Asociaciones sin ánimo de lucro.",
        )
        item.suitable_for_new_entity = True
        return item

    def test_fully_funded_grant_scores_five_out_of_five(self) -> None:
        item = self.financial_opportunity()
        item.funding_percentage = 100
        item.cofinancing_percentage = 0

        apply_caribdis_scoring(item)

        self.assertEqual(item.scoring.viability, 5)
        self.assertEqual(item.funding_instrument, "Subvención")
        self.assertIn("financiación del 100 %", item.financial_viability_reason)

    def test_seventy_percent_with_advance_scores_four(self) -> None:
        item = self.financial_opportunity()
        item.funding_percentage = 70
        item.cofinancing_percentage = 30
        item.advance_percentage = 40

        apply_caribdis_scoring(item)

        self.assertEqual(item.scoring.viability, 4)
        self.assertEqual(item.cashflow_risk, "Medio")

    def test_cofinancing_over_thirty_percent_is_severe(self) -> None:
        item = self.financial_opportunity()
        item.funding_percentage = 60
        item.cofinancing_percentage = 40
        item.advance_percentage = 0

        apply_caribdis_scoring(item)

        self.assertEqual(item.scoring.viability, 1)
        self.assertEqual(item.cashflow_risk, "Muy alto")

    def test_reimbursement_after_justification_has_high_cashflow_risk(self) -> None:
        item = self.financial_opportunity()
        item.funding_percentage = 100
        item.advance_percentage = 0
        item.reimbursement_only = True

        apply_caribdis_scoring(item)

        self.assertEqual(item.scoring.viability, 2)
        self.assertEqual(item.cashflow_risk, "Alto")
        self.assertIn("tras la justificación", item.financial_viability_reason)

    def test_two_year_seniority_is_not_suitable_for_new_entity(self) -> None:
        item = self.financial_opportunity()
        item.suitable_for_new_entity = None
        item.minimum_seniority = "Antigüedad mínima de dos años"

        apply_caribdis_scoring(item)

        self.assertFalse(item.suitable_for_new_entity)
        self.assertEqual(item.scoring.viability, 1)
        self.assertEqual(item.participation, "No elegible")

    def test_previous_experience_is_not_suitable_for_new_entity(self) -> None:
        item = self.financial_opportunity()
        item.suitable_for_new_entity = None
        item.previous_experience_required = True

        apply_caribdis_scoring(item)

        self.assertFalse(item.suitable_for_new_entity)
        self.assertEqual(item.scoring.viability, 1)
        self.assertEqual(item.priority, "Descartar")

    def test_operating_grant_is_identified(self) -> None:
        item = self.financial_opportunity()
        item.eligible_expenses = (
            "Gastos de funcionamiento, administración, gestoría, seguros y alquiler."
        )

        apply_caribdis_scoring(item)

        self.assertTrue(item.operating_costs_eligible)
        self.assertTrue(item.insurance_eligible)
        self.assertTrue(item.rent_eligible)
        self.assertIn("Ayuda para funcionamiento", item.funding_purposes)

    def test_scientific_communication_does_not_imply_operating_costs(self) -> None:
        item = self.financial_opportunity()
        item.raw_text = "Proyecto de comunicación social de la ciencia marina."

        apply_caribdis_scoring(item)

        self.assertIsNone(item.operating_costs_eligible)

    def test_staff_funding_is_identified(self) -> None:
        item = self.financial_opportunity()
        item.eligible_expenses = "Son subvencionables los gastos de personal y salarios."

        apply_caribdis_scoring(item)

        self.assertTrue(item.staff_costs_eligible)
        self.assertIn("Ayuda para personal", item.funding_purposes)

    def test_equipment_funding_is_identified(self) -> None:
        item = self.financial_opportunity()
        item.eligible_expenses = "Equipamiento científico y material inventariable."

        apply_caribdis_scoring(item)

        self.assertTrue(item.equipment_eligible)
        self.assertIn("Ayuda para equipamiento", item.funding_purposes)

    def test_donation_is_not_classified_as_public_grant(self) -> None:
        item = self.financial_opportunity()
        item.raw_text = "Donación privada para un proyecto de ciencia ciudadana marina."

        apply_caribdis_scoring(item)

        self.assertEqual(item.funding_instrument, "Donación")
        self.assertEqual(item.scoring.funding_type, 9)

    def test_sponsorship_is_not_classified_as_public_grant(self) -> None:
        item = self.financial_opportunity()
        item.raw_text = "Patrocinio empresarial para divulgación científica marina."

        apply_caribdis_scoring(item)

        self.assertEqual(item.funding_instrument, "Patrocinio")
        self.assertEqual(item.scoring.funding_type, 8)

    def test_call_can_be_explicitly_suitable_for_new_entity(self) -> None:
        item = self.financial_opportunity()

        apply_caribdis_scoring(item)

        self.assertTrue(item.suitable_for_new_entity)
        self.assertEqual(item.participation, "Solicitud directa")
        self.assertNotEqual(item.priority, "Descartar")

    def test_call_can_be_explicitly_unsuitable_for_new_entity(self) -> None:
        item = self.financial_opportunity()
        item.suitable_for_new_entity = False
        item.minimum_seniority = "Antigüedad mínima de dos años"

        apply_caribdis_scoring(item)

        self.assertFalse(item.suitable_for_new_entity)
        self.assertEqual(item.participation, "No elegible")
        self.assertEqual(item.priority, "Descartar")

    def test_recurrent_call_with_obtainable_requirements_is_monitored(self) -> None:
        item = self.financial_opportunity()
        item.suitable_for_new_entity = False
        item.minimum_seniority = "Antigüedad mínima de un año"
        item.recurrent = True

        apply_caribdis_scoring(item)

        self.assertEqual(item.participation, "Vigilar y preparar requisitos")
        self.assertNotEqual(item.priority, "Descartar")

    def test_closed_recurrent_partner_call_is_marked_for_next_edition(self) -> None:
        item = self.financial_opportunity()
        item.status = "Cerrada recurrente"
        item.recurrent = True
        item.beneficiaries = "Consorcio europeo internacional requerido."

        apply_caribdis_scoring(item)

        self.assertEqual(item.participation, "Vigilar próxima edición")
        self.assertNotEqual(item.priority, "Descartar")
        self.assertIn("exige consorcio internacional", item.risks)

    def test_consolidated_partner_path_is_preserved(self) -> None:
        item = self.financial_opportunity()
        item.suitable_for_new_entity = False
        item.partners_required = "Debe participar con una entidad socia consolidada."

        apply_caribdis_scoring(item)

        self.assertEqual(item.participation, "Participación mediante entidad socia")
        self.assertNotEqual(item.priority, "Descartar")


if __name__ == "__main__":
    unittest.main()
