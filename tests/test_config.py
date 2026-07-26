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
        self.assertTrue(all(source["coverage_type"] for source in config["sources"]))
        fecyt = next(source for source in config["sources"] if source["id"] == "fecyt")
        self.assertEqual(fecyt["adapter"], "verified")
        self.assertEqual(fecyt["opportunity"]["close_date"], "2026-09-16")
        priority_ids = {
            "fecyt",
            "fundacion_biodiversidad",
            "fundacion_unicaja",
            "fundacion_la_caixa",
            "galpa_cadiz",
            "galpa_huelva",
            "galpa_malaga",
            "galpa_alboran",
            "galpa_almeria_levante",
            "diputacion_sevilla",
            "diputacion_malaga",
            "diputacion_cadiz",
            "diputacion_huelva",
            "eu_life",
            "erasmus_plus",
            "cuerpo_europeo_solidaridad",
            "interreg_poCTEP",
            "interreg_sudoe",
            "interreg_euromed",
            "interreg_atlantic",
            "eu_funding_tenders",
        }
        configured = {source["id"]: source for source in config["sources"]}
        self.assertTrue(priority_ids.issubset(configured))
        self.assertTrue(all(configured[source_id]["coverage_type"] for source_id in priority_ids))


if __name__ == "__main__":
    unittest.main()
