import unittest

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
