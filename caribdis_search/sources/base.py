from __future__ import annotations

import json
import hashlib
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from ..models import Opportunity, SourceStatus


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36 "
    "CARIBDIS-Funding-Monitor/1.0"
)


class SourceError(RuntimeError):
    pass


@dataclass
class SourceContext:
    start_date: date
    end_date: date
    today: date
    timeout: int
    cache_dir: Path


def host_allowed(url: str, official_domains: list[str]) -> bool:
    hostname = (urllib.parse.urlsplit(url).hostname or "").lower()
    return any(hostname == domain.lower() or hostname.endswith(f".{domain.lower()}") for domain in official_domains)


def fetch_bytes(
    url: str,
    timeout: int,
    official_domains: list[str],
    retries: int = 3,
    respect_robots: bool = True,
    accept: str = "text/html,application/xhtml+xml,application/xml,application/json,*/*",
) -> bytes:
    if not host_allowed(url, official_domains):
        raise SourceError(f"Dominio fuera de la lista oficial: {url}")
    if respect_robots and not robots_allowed(url, timeout, official_domains):
        raise SourceError(f"robots.txt no permite consultar: {url}")

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
            "Connection": "close",
        },
    )
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read(12_000_000)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(1.5 * (attempt + 1))
    raise SourceError(f"No se pudo consultar {url}: {last_error}")


def robots_allowed(url: str, timeout: int, official_domains: list[str]) -> bool:
    parsed = urllib.parse.urlsplit(url)
    robots_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
    if not host_allowed(robots_url, official_domains):
        return False
    request = urllib.request.Request(robots_url, headers={"User-Agent": USER_AGENT})
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    try:
        with urllib.request.urlopen(request, timeout=min(timeout, 10)) as response:
            content = response.read(500_000).decode("utf-8", errors="replace")
        parser.parse(content.splitlines())
        return parser.can_fetch(USER_AGENT, url)
    except (urllib.error.URLError, TimeoutError, OSError):
        return True


def decode_payload(payload: bytes) -> str:
    for encoding in ("utf-8", "iso-8859-1", "windows-1252"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


def fetch_text(url: str, context: SourceContext, source: dict[str, Any]) -> str:
    cache_ttl = int(source.get("cache_ttl_seconds", 0))
    cache_path = context.cache_dir / f"{hashlib.sha256(url.encode('utf-8')).hexdigest()}.cache"
    if cache_ttl > 0 and cache_path.exists():
        age = time.time() - cache_path.stat().st_mtime
        if age <= cache_ttl:
            return cache_path.read_text(encoding="utf-8")
    payload = fetch_bytes(
        url,
        timeout=int(source.get("timeout", context.timeout)),
        official_domains=list(source["official_domains"]),
        retries=int(source.get("retries", 3)),
        respect_robots=bool(source.get("respect_robots", True)),
        accept=str(source.get("accept", "text/html,application/xhtml+xml,application/xml,application/json,*/*")),
    )
    text = decode_payload(payload)
    if cache_ttl > 0:
        context.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(text, encoding="utf-8")
    return text


def fetch_json(url: str, context: SourceContext, source: dict[str, Any], params: dict[str, Any]) -> Any:
    query = urllib.parse.urlencode(params)
    separator = "&" if "?" in url else "?"
    text = fetch_text(f"{url}{separator}{query}", context, source)
    return json.loads(text)


class BaseSource:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    @property
    def id(self) -> str:
        return str(self.config["id"])

    @property
    def name(self) -> str:
        return str(self.config["name"])

    def source_status(self, context: SourceContext) -> SourceStatus:
        coverage_type = str(self.config.get("coverage_type", "current"))
        configured_note = str(self.config.get("coverage_note", "")).strip()
        if coverage_type == "historical" or (
            coverage_type == "api"
            and bool(self.config.get("supports_date_filter", False))
        ):
            period_note = (
                f"Consulta del periodo {context.start_date.isoformat()} a "
                f"{context.end_date.isoformat()} con fechas y paginacion."
            )
        elif coverage_type == "api":
            period_note = (
                "API paginada del estado actual; no ofrece un filtro historico "
                "por fechas que acredite todo el periodo solicitado."
            )
        elif coverage_type == "rss":
            period_note = (
                "Solo elementos disponibles en el RSS; no acredita una revision "
                "completa del periodo solicitado."
            )
        else:
            period_note = (
                "Solo estado actual de la pagina; no acredita una revision "
                "historica completa del periodo solicitado."
            )
        return SourceStatus(
            source_id=self.id,
            source_name=self.name,
            coverage_type=coverage_type,
            coverage_note=" ".join(part for part in (configured_note, period_note) if part),
            requires_adjustment=bool(self.config.get("requires_adjustment", False)),
            adjustment_reason=str(self.config.get("adjustment_reason", "")),
        )

    def collect(self, context: SourceContext) -> list[Opportunity]:
        raise NotImplementedError
