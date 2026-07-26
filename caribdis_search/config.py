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
    if source["adapter"] not in {"bdns", "html", "rss"}:
        raise ConfigError(f"{filename} / {source['id']}: adaptador no soportado")


def load_configuration(config_dir: Path) -> dict[str, Any]:
    settings = load_json(config_dir / "caribdis.json")
    sources: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for filename in CONFIG_FILES:
        path = config_dir / filename
        if not path.exists():
            continue
        payload = load_json(path)
        if not isinstance(payload, list):
            raise ConfigError(f"{filename} debe contener una lista de fuentes")
        for source in payload:
            if not isinstance(source, dict):
                raise ConfigError(f"{filename} contiene una fuente no válida")
            validate_source(source, filename)
            if source["id"] in seen_ids:
                raise ConfigError(f"Identificador de fuente duplicado: {source['id']}")
            seen_ids.add(source["id"])
            source["_config_file"] = filename
            sources.append(source)
    settings["sources"] = sources
    return settings
