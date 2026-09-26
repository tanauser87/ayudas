import unittest
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

from caribdis_search.identity import extract_bdns_number
from caribdis_search.models import NOT_FOUND
from caribdis_search.scoring import apply_caribdis_scoring
from caribdis_search.sources.base import SourceContext
from caribdis_search.sources.base import SourceError
from caribdis_search.sources.bdns import (
    BDNSSource,
    is_prefilter_candidate,
    record_territory,
)


class BDNSSourceTests(unittest.TestCase):
    def source(self) -> BDNSSource:
        return BDNSSource(
            {
                "id": "bdns",
                "name": "BDNS",
                "group": "Estatal - BDNS",
                "adapter": "bdns",
                "url": "https://api.example.org/convocatorias/busqueda",
                "detail_api_url": "https://api.example.org/convocatorias",
                "fallback_urls": [],
                "detail_api_fallback_urls": [],
                "detail_url": "https://portal.example.org/convocatoria/{numeroConvocatoria}",
                "official_domains": ["example.org"],
                "page_size": 100,
                "max_pages": 100,
            }
        )

    def context(self, cache_dir: Path) -> SourceContext:
        return SourceContext(
            start_date=date(2026, 7, 20),
            end_date=date(2026, 7, 27),
            today=date(2026, 7, 27),
            timeout=1,
            cache_dir=cache_dir,
        )

    def list_record(
        self,
        number: str = "905627",
        title: str = "Ayudas para biodiversidad marina",
    ) -> dict[str, str]:
        return {
            "numeroConvocatoria": number,
            "fechaRecepcion": "25/07/2026",
            "descripcion": title,
            "nivel1": "ESTATAL",
            "nivel2": "MINISTERIO PARA LA TRANSICIÓN ECOLÓGICA",
        }

    def detail_record(
        self,
        number: str = "905627",
        title: str = "Ayudas para biodiversidad marina",
    ) -> dict[str, object]:
        return {
            "codigoBDNS": number,
            "descripcion": title,
            "organo": {
                "nivel1": "ESTATAL",
                "nivel2": "MINISTERIO PARA LA TRANSICIÓN ECOLÓGICA",
                "nivel3": "DIRECCIÓN GENERAL DE BIODIVERSIDAD",
            },
            "fechaRecepcion": "25/07/2026",
            "tipoConvocatoria": "Convocatoria en régimen de concurrencia competitiva",
            "presupuestoTotal": 150000,
            "descripcionFinalidad": "Conservación marina y ciencia ciudadana",
            "descripcionBasesReguladoras": "Bases para entidades sin ánimo de lucro",
            "urlBasesReguladoras": "https://boe.es/buscar/doc.php?id=BOE-A-2026-15000",
            "sedeElectronica": "https://sede.example.org/solicitud",
            "abierto": True,
            "fechaInicioSolicitud": "20/07/2026",
            "fechaFinSolicitud": "20/08/2026",
            "tiposBeneficiarios": [
                {"descripcion": "Asociaciones y entidades sin ánimo de lucro"}
            ],
            "instrumentos": [{"descripcion": "Subvención"}],
            "regiones": [{"descripcion": "Andalucía"}],
            "fondos": [{"descripcion": "FEMPA"}],
            "anuncios": [
                {
                    "titulo": "Extracto de la convocatoria",
                    "texto": (
                        "Gastos subvencionables de seguimiento de fauna marina. "
                        "Financiación del 80 %. Importe máximo 50.000 euros. "
                        "Se prevé anticipo sin necesidad de aval."
                    ),
                    "url": "https://boe.es/diario_boe/txt.php?id=BOE-B-2026-12345",
                    "cve": "BOE-B-2026-12345",
                    "datPublicacion": "24/07/2026",
                }
            ],
        }

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

    def test_extracts_bdns_number_from_official_extract(self) -> None:
        number = extract_bdns_number(
            "Extracto de la convocatoria. BDNS (Identif.): 905627."
        )

        self.assertEqual(number, "905627")

    def test_prefilter_requires_potential_caribdis_terms(self) -> None:
        self.assertTrue(
            is_prefilter_candidate(
                self.list_record(title="Ayudas para entidades sin ánimo de lucro")
            )
        )
        self.assertFalse(
            is_prefilter_candidate(
                self.list_record(title="Ayudas para modernización industrial")
            )
        )

    @patch("caribdis_search.sources.bdns.fetch_json")
    def test_bdns_uses_dates_and_real_pagination(self, fetch_json_mock) -> None:
        def response(url, _context, _config, params):
            if url.endswith("/busqueda"):
                if params["page"] == 0:
                    return {
                        "content": [self.list_record()],
                        "last": False,
                        "totalPages": 2,
                    }
                return {"content": [], "last": True, "totalPages": 2}
            return self.detail_record()

        fetch_json_mock.side_effect = response
        source = self.source()
        with tempfile.TemporaryDirectory() as temporary_directory:
            opportunities = source.collect(self.context(Path(temporary_directory)))

        self.assertEqual(len(opportunities), 1)
        list_calls = [
            call for call in fetch_json_mock.call_args_list
            if call.args[0].endswith("/busqueda")
        ]
        self.assertEqual(len(list_calls), 2)
        first_params = list_calls[0].args[3]
        second_params = list_calls[1].args[3]
        self.assertEqual(first_params["fechaDesde"], "20/07/2026")
        self.assertEqual(first_params["fechaHasta"], "27/07/2026")
        self.assertEqual(first_params["page"], 0)
        self.assertEqual(second_params["page"], 1)

    @patch("caribdis_search.sources.bdns.fetch_json")
    def test_enriches_valid_call_for_associations(self, fetch_json_mock) -> None:
        def response(url, _context, _config, _params):
            if url.endswith("/busqueda"):
                return {
                    "content": [self.list_record()],
                    "last": True,
                    "totalPages": 1,
                }
            return self.detail_record()

        fetch_json_mock.side_effect = response
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = self.source().collect(self.context(Path(temporary_directory)))[0]

        self.assertEqual(result.bdns_number, "905627")
        self.assertEqual(result.open_date, "2026-07-20")
        self.assertEqual(result.close_date, "2026-08-20")
        self.assertEqual(result.status, "Abierta")
        self.assertEqual(result.solicitability, "Solicitable")
        self.assertIn("entidades sin ánimo de lucro", result.beneficiaries)
        self.assertEqual(result.total_budget, "150.000,00 EUR")
        self.assertEqual(result.financing_rate, "80 %")
        self.assertIn("FEMPA", result.european_funds)
        self.assertIn("BOE-B-2026-12345", result.official_identifiers)
        self.assertTrue(result.detail_enriched)
        self.assertTrue(result.metadata_verified)

    @patch("caribdis_search.sources.bdns.fetch_json")
    def test_direct_grant_is_classified_and_discarded(self, fetch_json_mock) -> None:
        detail = self.detail_record(
            title="Concesión directa para conservación marina"
        )
        detail["tipoConvocatoria"] = "Concesión directa"

        def response(url, _context, _config, _params):
            if url.endswith("/busqueda"):
                return {
                    "content": [
                        self.list_record(
                            title="Concesión directa para conservación marina"
                        )
                    ],
                    "last": True,
                }
            return detail

        fetch_json_mock.side_effect = response
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = self.source().collect(self.context(Path(temporary_directory)))[0]
        apply_caribdis_scoring(result)

        self.assertEqual(result.record_type, "Concesión directa")
        self.assertEqual(result.solicitability, "Concesión directa")
        self.assertEqual(result.priority, "Descartar")
        self.assertEqual(result.participation, "No elegible")

    @patch("caribdis_search.sources.bdns.fetch_json")
    def test_resolved_call_is_not_solicitable(self, fetch_json_mock) -> None:
        detail = self.detail_record()
        detail["abierto"] = False
        detail["anuncios"] = [
            {
                "titulo": "Resolución de concesión",
                "texto": "Relación definitiva de beneficiarios de las subvenciones concedidas.",
                "url": "https://boe.es/diario_boe/txt.php?id=BOE-A-2026-16000",
                "cve": "BOE-A-2026-16000",
                "datPublicacion": "26/07/2026",
            }
        ]

        def response(url, _context, _config, _params):
            if url.endswith("/busqueda"):
                return {
                    "content": [self.list_record()],
                    "last": True,
                }
            return detail

        fetch_json_mock.side_effect = response
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = self.source().collect(self.context(Path(temporary_directory)))[0]
        apply_caribdis_scoring(result)

        self.assertEqual(result.record_type, "Convocatoria ya resuelta")
        self.assertEqual(result.solicitability, "Convocatoria ya resuelta")
        self.assertEqual(result.priority, "Descartar")

    @patch("caribdis_search.sources.bdns.fetch_json")
    def test_detail_failure_does_not_stop_search(self, fetch_json_mock) -> None:
        records = [
            self.list_record("905627", "Ayuda a asociaciones para medio marino"),
            self.list_record("905628", "Ayuda a ONG para biodiversidad marina"),
        ]

        def response(url, _context, _config, params):
            if url.endswith("/busqueda"):
                return {"content": records, "last": True}
            if params["numConv"] == "905627":
                raise SourceError("detalle temporalmente no disponible")
            return self.detail_record("905628")

        fetch_json_mock.side_effect = response
        source = self.source()
        with tempfile.TemporaryDirectory() as temporary_directory:
            results = source.collect(self.context(Path(temporary_directory)))

        self.assertEqual(len(results), 2)
        failed = next(item for item in results if item.bdns_number == "905627")
        enriched = next(item for item in results if item.bdns_number == "905628")
        self.assertFalse(failed.detail_enriched)
        self.assertTrue(failed.warnings)
        self.assertTrue(enriched.detail_enriched)
        self.assertEqual(len(source.errors), 1)

    @patch("caribdis_search.sources.bdns.fetch_json")
    def test_irrelevant_list_record_does_not_fetch_detail(self, fetch_json_mock) -> None:
        fetch_json_mock.return_value = {
            "content": [
                self.list_record(title="Ayudas para modernización industrial")
            ],
            "last": True,
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            results = self.source().collect(self.context(Path(temporary_directory)))

        self.assertEqual(results, [])
        self.assertEqual(fetch_json_mock.call_count, 1)
        self.assertEqual(
            extract_bdns_number("Texto sin identificador"),
            NOT_FOUND,
        )


if __name__ == "__main__":
    unittest.main()
