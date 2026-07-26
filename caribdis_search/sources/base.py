from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from ..models import Opportunity


USER_AGENT = "CARIBDIS-Funding-Monitor/1.0"


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
) -> bytes:
    if not host_allowed(url, official_domains):
        raise SourceError(f"Dominio fuera de la lista oficial: {url}")
    if respect_robots and not robots_allowed(url, timeout, official_domains):
        raise SourceError(f"robots.txt no permite consultar: {url}")

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml,application/json,*/*",
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
    payload = fetch_bytes(
        url,
        timeout=int(source.get("timeout", context.timeout)),
        official_domains=list(source["official_domains"]),
        retries=int(source.get("retries", 3)),
        respect_robots=bool(source.get("respect_robots", True)),
    )
    return decode_payload(payload)


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

    def collect(self, context: SourceContext) -> list[Opportunity]:
        raise NotImplementedError
