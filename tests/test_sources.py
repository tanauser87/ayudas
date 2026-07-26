import unittest

from caribdis_search.sources.bdns import record_territory


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


if __name__ == "__main__":
    unittest.main()
