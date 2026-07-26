import unittest
from pathlib import Path

from caribdis_search.config import load_configuration


class ConfigTests(unittest.TestCase):
    def test_loads_unique_official_sources(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]

        config = load_configuration(repository_root / "config")

        source_ids = [source["id"] for source in config["sources"]]
        self.assertIn("bdns", source_ids)
        self.assertIn("fecyt", source_ids)
        self.assertEqual(len(source_ids), len(set(source_ids)))
        self.assertTrue(all(source["official_domains"] for source in config["sources"]))
        self.assertEqual(
            sum(source["group"] == "Diputaciones andaluzas" for source in config["sources"]),
            8,
        )
        municipalities = {
            source.get("municipality")
            for source in config["sources"]
            if source["group"] == "Ayuntamientos y entidades locales"
        }
        self.assertIn("Tarifa", municipalities)
        self.assertIn("Nerja", municipalities)
        self.assertIn("Pulpí", municipalities)
        self.assertIn("galpa_cadiz", source_ids)
        self.assertIn("galpa_huelva", source_ids)
        self.assertIn("galpa_malaga", source_ids)
        self.assertIn("eu_life", source_ids)
        self.assertIn("eu_horizon", source_ids)
        self.assertIn("interreg_poCTEP", source_ids)
        horizon = next(source for source in config["sources"] if source["id"] == "eu_horizon")
        self.assertIn("Consorcio europeo", horizon["consortium_hint"])
        self.assertIn("fundacion_la_caixa", source_ids)
        self.assertIn("fundacion_once", source_ids)
        self.assertIn("fundacion_moeve", source_ids)


if __name__ == "__main__":
    unittest.main()
