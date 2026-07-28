import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from caribdis_search.history import deduplicate
from caribdis_search.models import Opportunity
from caribdis_search.runner import create_sources
from caribdis_search.scoring import apply_caribdis_scoring
from caribdis_search.sources.base import SourceContext, SourceError
from caribdis_search.sources.junta_procedures import (
    DETAIL_PATH,
    EU_FUNDS_PATH,
    FRONT_DETAIL_PATH,
    SEARCH_PATH,
    SUBSIDY_FAMILY,
    JuntaProceduresSource,
    analyze_openapi,
)


def parameters(*names: str) -> list[dict[str, str]]:
    return [{"name": name} for name in names]


def openapi_fixture() -> dict[str, object]:
    return {
        "openapi": "3.0.2",
        "paths": {
            SEARCH_PATH: {
                "get": {
                    "summary": "Búsqueda paginada",
                    "parameters": parameters(
                        "status",
                        "topic",
                        "counseling",
                        "organism",
                        "family",
                        "activity",
                        "search_text",
                        "order_by",
                        "mode",
                        "format",
                        "size",
                        "page",
                    ),
                }
            },
            DETAIL_PATH: {
                "get": {
                    "summary": "Detalle",
                    "parameters": parameters("bid"),
                }
            },
            FRONT_DETAIL_PATH: {
                "get": {
                    "summary": "Detalle de presentación",
                    "parameters": parameters("bid"),
                }
            },
            EU_FUNDS_PATH: {
                "get": {
                    "summary": "Fondos europeos",
                    "parameters": parameters(
                        "status",
                        "counseling",
                        "organism",
                        "eufunds",
                        "search_text",
                        "order_by",
                        "mode",
                        "format",
                        "size",
                        "page",
                    ),
                }
            },
        },
        "components": {
            "schemas": {
                "_Enum_Families": {"enum": ["-", SUBSIDY_FAMILY]},
                "_Enum_Eufunds": {
                    "enum": ["-", "FEADER", "FEDER", "FEMPA", "FSE+", "FTJ", "MRR"]
                },
            }
        },
    }


def detail_fixture(
    code: str = "24468",
    *,
    state: str = "Abierto",
    family: str = SUBSIDY_FAMILY,
    title: str = "Subvenciones para biodiversidad marina",
    eufunds: str = "NA",
    requirements: str = (
        "Podrán solicitarlas asociaciones sin ánimo de lucro legalmente inscritas."
    ),
) -> dict[str, object]:
    return {
        "id": int(code),
        "title": title,
        "description": (
            "Proyectos de conservación del medio marino, biodiversidad y "
            "educación ambiental en Andalucía."
        ),
        "state": state,
        "family": family,
        "topic": "Medio ambiente",
        "counseling": "Sostenibilidad y Medio Ambiente",
        "managing_organism": "D. G. de Biodiversidad",
        "recipient_name": ["Asociaciones y organizaciones"],
        "requirements": requirements,
        "application_deadline_type": "Determinado",
        "application_start_date": ["2026-07-20T00:00:00.000Z"],
        "application_end_date": ["2026-08-20T23:59:00.000Z"],
        "legal_basis_title": ["Orden reguladora"],
        "legal_basis_url": [
            "https://www.juntadeandalucia.es/boja/2026/100/1.html"
        ],
        "form_name": ["Solicitud"],
        "form_url": ["https://www.juntadeandalucia.es/formulario.pdf"],
        "online_service_url": "https://www.juntadeandalucia.es/solicitud",
        "processing_body_name": ["D. G. de Biodiversidad"],
        "created_date": "2026-06-01T00:00:00.000Z",
        "publication_date": "2026-07-20T00:00:00.000Z",
        "last_updated_date": "2026-07-20T10:00:00.000Z",
        "eufunds": eufunds,
        "novelties_description": ["Convocatoria 2026"],
    }


class JuntaProceduresTests(unittest.TestCase):
    def source(self, watchlist: list[str] | None = None) -> JuntaProceduresSource:
        return JuntaProceduresSource(
            {
                "id": "junta_catalogo_procedimientos",
                "name": "Junta - API de procedimientos",
                "group": "Junta de Andalucía",
                "adapter": "junta_procedures",
                "url": f"https://datos.example.org{SEARCH_PATH}",
                "detail_api_url": "https://datos.example.org/api/v0/procedures/{bid}",
                "front_detail_api_url": (
                    "https://datos.example.org/api/v0/procedures/"
                    "frontsearchdetails/{bid}"
                ),
                "eu_funds_url": f"https://datos.example.org{EU_FUNDS_PATH}",
                "openapi_url": "https://datos.example.org/api/v0/procedures/openapi.json",
                "public_url_template": (
                    "https://junta.example.org/procedimientos/detalle/{bid}.html"
                ),
                "official_domains": ["example.org"],
                "organization_type": "Administración autonómica",
                "page_size": 2,
                "max_pages": 100,
                "procedure_watchlist": watchlist or [],
            }
        )

    def context(self, cache_dir: Path) -> SourceContext:
        return SourceContext(
            start_date=date(2026, 7, 15),
            end_date=date(2026, 7, 28),
            today=date(2026, 7, 28),
            timeout=1,
            cache_dir=cache_dir,
        )

    def test_reads_documented_openapi_contract(self) -> None:
        analysis = analyze_openapi(openapi_fixture())

        self.assertTrue(analysis[SEARCH_PATH]["paginated"])
        self.assertIn("family", analysis[SEARCH_PATH]["parameters"])
        self.assertIn("eufunds", analysis[EU_FUNDS_PATH]["parameters"])
        self.assertIn("FEMPA", analysis["european_funds"]["values"])

    def test_rejects_undocumented_endpoint(self) -> None:
        specification = openapi_fixture()
        del specification["paths"][EU_FUNDS_PATH]

        with self.assertRaisesRegex(SourceError, "no documenta"):
            analyze_openapi(specification)

    @patch("caribdis_search.sources.junta_procedures.fetch_json")
    def test_uses_subsidy_filter_and_complete_pagination(self, fetch_json_mock) -> None:
        def response(url, _context, _config, params):
            if url.endswith("openapi.json"):
                return openapi_fixture()
            if url.endswith(SEARCH_PATH):
                page = params["page"]
                code = "1001" if page == 0 else "1002"
                return {
                    "results": [
                        {
                            "id": int(code),
                            "name": f"Subvención {code} para biodiversidad",
                            "description": "Medio ambiente y asociaciones",
                            "state": "Abierto",
                        }
                    ],
                    "paginacion": {
                        "totalPaginas": 2,
                        "numeroPagina": page + 1,
                    },
                }
            if url.endswith(EU_FUNDS_PATH):
                return {
                    "results": [],
                    "paginacion": {"totalPaginas": 1, "numeroPagina": 1},
                }
            code = url.rsplit("/", 1)[-1]
            return {"hits": 1, "results": [detail_fixture(code)]}

        fetch_json_mock.side_effect = response
        with tempfile.TemporaryDirectory() as temporary_directory:
            results = self.source().collect(
                self.context(Path(temporary_directory))
            )

        search_calls = [
            call
            for call in fetch_json_mock.call_args_list
            if call.args[0].endswith(SEARCH_PATH)
        ]
        self.assertEqual([call.args[3]["page"] for call in search_calls], [0, 1])
        self.assertTrue(
            all(call.args[3]["family"] == SUBSIDY_FAMILY for call in search_calls)
        )
        self.assertEqual({item.procedure_code for item in results}, {"1001", "1002"})

    def test_maps_open_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            item = self.source()._build_opportunity(
                detail_fixture(state="Abierto"),
                self.context(Path(temporary_directory)),
            )

        self.assertEqual(item.status, "Abierta")
        self.assertEqual(item.solicitability, "Solicitable")
        self.assertEqual(item.counseling, "Sostenibilidad y Medio Ambiente")

    def test_maps_closed_status(self) -> None:
        record = detail_fixture(state="Cerrado")
        record["application_end_date"] = ["2026-07-10T23:59:00.000Z"]
        with tempfile.TemporaryDirectory() as temporary_directory:
            item = self.source()._build_opportunity(
                record,
                self.context(Path(temporary_directory)),
            )

        self.assertEqual(item.status, "Cerrada")
        self.assertEqual(item.solicitability, "Referencia histórica")

    def test_detects_fempa(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            item = self.source()._build_opportunity(
                detail_fixture(eufunds="FEMPA"),
                self.context(Path(temporary_directory)),
            )

        self.assertEqual(item.european_funds, ["FEMPA"])

    def test_identifies_procedure_for_new_association(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            item = self.source()._build_opportunity(
                detail_fixture(),
                self.context(Path(temporary_directory)),
            )

        self.assertTrue(item.financial_opportunity)
        self.assertIn("Sí", item.new_association_eligibility)
        self.assertIn("Asociaciones", item.beneficiaries)

    def test_distinguishes_watchlist_program_and_center_requirements(self) -> None:
        record = detail_fixture(
            requirements=(
                "Para la modalidad de programa, entidades de voluntariado sin "
                "ánimo de lucro inscritas. Para la modalidad de gestión de "
                "centros, haber funcionado al menos 4 meses."
            )
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            item = self.source()._build_opportunity(
                record,
                self.context(Path(temporary_directory)),
            )

        self.assertIn("Sí para la modalidad de programas", item.new_association_eligibility)
        self.assertIn("funcionamiento previo", item.new_association_eligibility)

    def test_non_financial_registration_has_no_funding_score(self) -> None:
        record = detail_fixture(
            code="15802",
            family=(
                "Familia 1. Comunicaciones previas, autorizaciones, "
                "acreditaciones, e inscripciones registrales"
            ),
            title="Autorización e inscripción de entidades colaboradoras",
            requirements="Se exige personalidad jurídica y experiencia técnica.",
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            item = self.source()._build_opportunity(
                record,
                self.context(Path(temporary_directory)),
            )
        apply_caribdis_scoring(item)

        self.assertTrue(item.strategic_procedure)
        self.assertFalse(item.financial_opportunity)
        self.assertEqual(item.caribdis_score, 0)
        self.assertEqual(item.priority, "Descartar")
        self.assertEqual(item.solicitability, "Trámite estratégico no económico")

    @patch("caribdis_search.sources.junta_procedures.fetch_json")
    def test_watchlist_fetches_procedure_not_present_in_search(
        self,
        fetch_json_mock,
    ) -> None:
        def response(url, _context, _config, _params):
            if url.endswith("openapi.json"):
                return openapi_fixture()
            if url.endswith((SEARCH_PATH, EU_FUNDS_PATH)):
                return {
                    "results": [],
                    "paginacion": {"totalPaginas": 1, "numeroPagina": 1},
                }
            return {"hits": 1, "results": [detail_fixture("15802")]}

        fetch_json_mock.side_effect = response
        with tempfile.TemporaryDirectory() as temporary_directory:
            results = self.source(["15802"]).collect(
                self.context(Path(temporary_directory))
            )

        self.assertEqual([item.procedure_code for item in results], ["15802"])

    @patch("caribdis_search.sources.junta_procedures.fetch_json")
    def test_watchlist_does_not_keep_unverified_code(
        self,
        fetch_json_mock,
    ) -> None:
        def response(url, _context, _config, _params):
            if url.endswith("openapi.json"):
                return openapi_fixture()
            if url.endswith((SEARCH_PATH, EU_FUNDS_PATH)):
                return {
                    "results": [],
                    "paginacion": {"totalPaginas": 1, "numeroPagina": 1},
                }
            return {"hits": 0, "results": []}

        fetch_json_mock.side_effect = response
        source = self.source(["99999"])
        with tempfile.TemporaryDirectory() as temporary_directory:
            results = source.collect(self.context(Path(temporary_directory)))

        self.assertEqual(results, [])
        self.assertEqual(len(source.errors), 1)

    def test_deduplicates_junta_boja_and_bdns(self) -> None:
        junta = Opportunity(
            source="API Junta",
            source_references=["API Junta"],
            procedure_code="24468",
            bdns_number="900001",
            official_identifiers=["JUNTA-PROC-24468", "BOJA-2026-100-1"],
            title="Subvenciones para voluntariado ambiental",
            organization="Junta de Andalucía",
            published_date="2026-07-20",
            official_url=(
                "https://www.juntadeandalucia.es/servicios/sede/tramites/"
                "procedimientos/detalle/24468.html"
            ),
            detail_enriched=True,
        )
        boja = Opportunity(
            source="BOJA",
            source_references=["BOJA"],
            title="Extracto de subvenciones para voluntariado ambiental",
            organization="Junta de Andalucía",
            published_date="2026-07-20",
            official_url="https://www.juntadeandalucia.es/boja/2026/100/1.html",
            raw_text="Código procedimiento: 24468. BOJA-2026-100-1.",
        )
        bdns = Opportunity(
            source="BDNS",
            source_references=["BDNS"],
            bdns_number="900001",
            title="Subvenciones para voluntariado ambiental",
            organization="Junta de Andalucía",
            published_date="2026-07-20",
            official_url="https://www.subvenciones.gob.es/convocatoria/900001",
        )

        results = deduplicate([boja, bdns, junta])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].procedure_code, "24468")
        self.assertEqual(results[0].bdns_number, "900001")
        self.assertEqual(
            set(results[0].source_references),
            {"API Junta", "BOJA", "BDNS"},
        )

    @patch("caribdis_search.sources.junta_procedures.fetch_json")
    def test_partial_api_failure_does_not_stop_other_results(
        self,
        fetch_json_mock,
    ) -> None:
        def response(url, _context, _config, _params):
            if url.endswith("openapi.json"):
                return openapi_fixture()
            if url.endswith(SEARCH_PATH):
                return {
                    "results": [
                        {
                            "id": 1001,
                            "name": "Ayuda para biodiversidad",
                            "description": "Medio ambiente y asociaciones",
                        },
                        {
                            "id": 1002,
                            "name": "Ayuda para educación ambiental",
                            "description": "Asociaciones y educación ambiental",
                        },
                    ],
                    "paginacion": {"totalPaginas": 1, "numeroPagina": 1},
                }
            if url.endswith(EU_FUNDS_PATH):
                raise SourceError("fallo parcial de fondos europeos")
            if url.endswith("/1001"):
                raise SourceError("detalle no disponible")
            return {"hits": 1, "results": [detail_fixture("1002")]}

        fetch_json_mock.side_effect = response
        source = self.source()
        with tempfile.TemporaryDirectory() as temporary_directory:
            results = source.collect(self.context(Path(temporary_directory)))

        self.assertEqual([item.procedure_code for item in results], ["1002"])
        self.assertEqual(len(source.errors), 2)

    def test_runner_creates_specific_adapter(self) -> None:
        source_config = self.source().config
        sources = create_sources(
            {
                "legacy_boe_boja_enabled": False,
                "sources": [source_config],
            }
        )

        self.assertEqual(len(sources), 1)
        self.assertIsInstance(sources[0], JuntaProceduresSource)


if __name__ == "__main__":
    unittest.main()
