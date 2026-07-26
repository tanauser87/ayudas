import unittest
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

from caribdis_search.sources.base import SourceContext
from caribdis_search.sources.bdns import BDNSSource, record_territory


class BDNSSourceTests(unittest.TestCase):
    def test_keeps_andalusian_local_scope(self) -> None:
        territory, province = record_territory(
            {
                "nivel1": "LOCAL",
                "nivel2": "DIPUTACIÓN PROV. DE GRANADA",
                "nivel3": "DIPUTACIÓN PROVINCIAL DE GRANADA",
            }
        )

        self.assertEqual(territory, "Andalucía")
        self.assertEqual(province, "Granada")

    def test_marks_other_local_scope_outside_andalusia(self) -> None:
        territory, province = record_territory(
            {
                "nivel1": "LOCAL",
                "nivel2": "CASTRO-URDIALES",
                "nivel3": "AYUNTAMIENTO DE CASTRO-URDIALES",
            }
        )

        self.assertEqual(territory, "Fuera de Andalucía")
        self.assertEqual(province, "Dato no localizado")

    def test_keeps_state_scope(self) -> None:
        territory, _ = record_territory({"nivel1": "ESTATAL", "nivel2": "MINISTERIO"})

        self.assertEqual(territory, "España")

    @patch("caribdis_search.sources.bdns.fetch_json")
    def test_bdns_uses_dates_and_real_pagination(self, fetch_json_mock) -> None:
        fetch_json_mock.side_effect = [
            {
                "content": [
                    {
                        "numeroConvocatoria": "123",
                        "fechaRecepcion": "25/07/2026",
                        "descripcion": "Subvención para biodiversidad marina",
                        "nivel1": "ESTATAL",
                        "nivel2": "MINISTERIO",
                    }
                ],
                "last": False,
                "totalPages": 2,
            },
            {"content": [], "last": True, "totalPages": 2},
        ]
        source = BDNSSource(
            {
                "id": "bdns",
                "name": "BDNS",
                "group": "Estatal - BDNS",
                "adapter": "bdns",
                "url": "https://example.org/api",
                "detail_url": "https://example.org/call/{numeroConvocatoria}",
                "official_domains": ["example.org"],
                "page_size": 100,
                "max_pages": 100,
            }
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            context = SourceContext(
                start_date=date(2026, 7, 20),
                end_date=date(2026, 7, 27),
                today=date(2026, 7, 27),
                timeout=1,
                cache_dir=Path(temporary_directory),
            )
            opportunities = source.collect(context)

        self.assertEqual(len(opportunities), 1)
        self.assertEqual(fetch_json_mock.call_count, 2)
        first_params = fetch_json_mock.call_args_list[0].args[3]
        second_params = fetch_json_mock.call_args_list[1].args[3]
        self.assertEqual(first_params["fechaDesde"], "20/07/2026")
        self.assertEqual(first_params["fechaHasta"], "27/07/2026")
        self.assertEqual(first_params["page"], 0)
        self.assertEqual(second_params["page"], 1)


if __name__ == "__main__":
    unittest.main()
