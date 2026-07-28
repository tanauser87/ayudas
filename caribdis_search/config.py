from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CONFIG_FILES = [
    "fuentes_estatales.json",
    "fuentes_andalucia.json",
    "diputaciones.json",
    "ayuntamientos.json",
    "fuentes_galp.json",
    "fuentes_europeas.json",
    "fundaciones.json",
]


class ConfigError(ValueError):
    pass


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"No existe el archivo de configuración: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"JSON no válido en {path}: {exc}") from exc


def validate_source(source: dict[str, Any], filename: str) -> None:
    required = {"id", "name", "group", "adapter", "url", "official_domains"}
    missing = sorted(required - source.keys())
    if missing:
        raise ConfigError(f"{filename} / {source.get('id', 'sin id')}: faltan {', '.join(missing)}")
    if not source["official_domains"]:
        raise ConfigError(f"{filename} / {source['id']}: official_domains no puede estar vacío")
    if source["adapter"] not in {
        "bdns",
        "html",
        "junta_procedures",
        "rss",
        "verified",
    }:
        raise ConfigError(f"{filename} / {source['id']}: adaptador no soportado")
    if source["adapter"] == "junta_procedures":
        junta_required = {
            "detail_api_url",
            "eu_funds_url",
            "front_detail_api_url",
            "openapi_url",
            "procedure_watchlist",
            "public_url_template",
        }
        junta_missing = sorted(junta_required - source.keys())
        if junta_missing:
            raise ConfigError(
                f"{filename} / {source['id']}: faltan metadatos Junta "
                f"{', '.join(junta_missing)}"
            )
        if not isinstance(source["procedure_watchlist"], list):
            raise ConfigError(
                f"{filename} / {source['id']}: procedure_watchlist debe ser una lista"
            )
    if source.get("coverage_type") not in {"historical", "api", "rss", "current", "landing"}:
        raise ConfigError(f"{filename} / {source['id']}: coverage_type no válido")


def load_configuration(config_dir: Path) -> dict[str, Any]:
    settings = load_json(config_dir / "caribdis.json")
    sources: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for filename in CONFIG_FILES:
        path = config_dir / filename
        if not path.exists():
            continue
        payload = load_json(path)
        defaults: dict[str, Any] = {}
        if isinstance(payload, dict):
            defaults = payload.get("defaults", {})
            payload = payload.get("sources", [])
        if not isinstance(payload, list):
            raise ConfigError(f"{filename} debe contener una lista de fuentes o un objeto con sources")
        for raw_source in payload:
            source = {**defaults, **raw_source} if isinstance(raw_source, dict) else raw_source
            if not isinstance(source, dict):
                raise ConfigError(f"{filename} contiene una fuente no válida")
            source.setdefault(
                "coverage_type",
                {
                    "bdns": "api",
                    "junta_procedures": "api",
                    "rss": "rss",
                    "verified": "current",
                }.get(
                    str(source.get("adapter")), "current"
                ),
            )
            source.setdefault("coverage_note", "")
            validate_source(source, filename)
            if source["id"] in seen_ids:
                raise ConfigError(f"Identificador de fuente duplicado: {source['id']}")
            seen_ids.add(source["id"])
            source["_config_file"] = filename
            sources.append(source)
    settings["sources"] = sources
    return settings
