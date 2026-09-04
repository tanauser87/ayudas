import unittest
from unittest.mock import patch

from caribdis_search import history as history_module
from caribdis_search.history import (
    apply_recurrence,
    deduplicate,
    empty_history,
    update_history,
)
from caribdis_search.models import Opportunity


class HistoryTests(unittest.TestCase):
    def test_deduplicates_by_canonical_url_and_keeps_richer_record(self) -> None:
        basic = Opportunity(
            title="Ayuda marina",
            official_url="https://example.org/ayuda/?utm_source=newsletter",
        )
        rich = Opportunity(
            title="Ayuda marina",
            official_url="https://example.org/ayuda/",
            max_amount="50.000 €",
            beneficiaries="Asociaciones sin ánimo de lucro",
        )

        result = deduplicate([basic, rich])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].max_amount, "50.000 €")

    def test_deduplicates_bdns_and_boe_and_preserves_both_sources(self) -> None:
        bdns = Opportunity(
            source_id="bdns",
            source="BDNS",
            source_references=["BDNS"],
            bdns_number="905627",
            official_identifiers=["BOE-B-2026-12345"],
            title="Ayudas para biodiversidad marina",
            organization="Ministerio para la Transición Ecológica",
            published_date="2026-07-24",
            official_url="https://www.subvenciones.gob.es/convocatoria/905627",
            total_budget="150.000 EUR",
            detail_enriched=True,
        )
        boe = Opportunity(
            source_id="boe_boja",
            source="BOE",
            source_references=["BOE"],
            title="Extracto de ayudas para biodiversidad marina",
            organization="Ministerio para la Transición Ecológica",
            published_date="2026-07-24",
            official_url="https://www.boe.es/diario_boe/txt.php?id=BOE-B-2026-12345",
            raw_text="BDNS (Identif.): 905627. CVE BOE-B-2026-12345.",
        )

        result = deduplicate([boe, bdns])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].bdns_number, "905627")
        self.assertEqual(set(result[0].source_references), {"BDNS", "BOE"})
        self.assertIn("BOE-B-2026-12345", result[0].official_identifiers)
        self.assertIn(boe.official_url, result[0].official_links)
        self.assertEqual(result[0].total_budget, "150.000 EUR")

    def test_does_not_deduplicate_only_by_title(self) -> None:
        first = Opportunity(
            title="Ayudas para educación ambiental",
            organization="Diputación de Cádiz",
            published_date="2026-07-20",
        )
        second = Opportunity(
            title=first.title,
            organization="Diputación de Huelva",
            published_date="2026-07-21",
        )

        result = deduplicate([first, second])

        self.assertEqual(len(result), 2)

    def test_deduplication_does_not_reextract_every_pair(self) -> None:
        opportunities = [
            Opportunity(
                title=f"Convocatoria ambiental {index}",
                organization="Organismo de prueba",
                published_date="2026-07-20",
                official_url=f"https://example.org/convocatoria/{index}",
                raw_text="biodiversidad marina " * 1_000,
            )
            for index in range(80)
        ]

        with patch.object(
            history_module,
            "populate_official_identity",
            wraps=history_module.populate_official_identity,
        ) as populate_mock:
            result = deduplicate(opportunities)

        self.assertEqual(len(result), len(opportunities))
        self.assertLessEqual(
            populate_mock.call_count,
            len(opportunities) * 2,
        )

    def test_detects_deadline_change(self) -> None:
        previous = Opportunity(
            id="same",
            title="Convocatoria de biodiversidad marina",
            official_url="https://example.org/call",
            close_date="2026-08-01",
            first_seen="2026-07-01T10:00:00+02:00",
        )
        history = empty_history()
        history["opportunities"]["same"] = previous.to_dict()
        current = Opportunity(
            id="same",
            title=previous.title,
            official_url=previous.official_url,
            close_date="2026-08-15",
        )

        updated = update_history([current], history, "2026-07-26T10:00:00+02:00")

        self.assertIn("cambio de plazo", current.changes[0])
        self.assertEqual(len(updated["events"]), 1)

    def test_marks_recurrence_and_labels_estimate(self) -> None:
        history = empty_history()
        for year in (2024, 2025):
            previous = Opportunity(
                id=str(year),
                title=f"Convocatoria {year} de ciencia ciudadana marina",
                published_date=f"{year}-06-15",
            )
            history["opportunities"][previous.id] = previous.to_dict()
        current = Opportunity(
            id="2026",
            title="Convocatoria 2026 de ciencia ciudadana marina",
            published_date="2026-06-15",
            status="Cerrada",
        )

        apply_recurrence([current], history)

        self.assertTrue(current.recurrent)
        self.assertEqual(current.status, "Cerrada recurrente")
        self.assertTrue(current.estimated_next_call.startswith("Estimación histórica:"))


if __name__ == "__main__":
    unittest.main()
