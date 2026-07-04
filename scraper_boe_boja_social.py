#!/usr/bin/env python3
"""Scraper diario de BOE y BOJA para subvenciones de entidades sociales.

Pensado para ejecutarse en GitHub Actions sin dependencias externas. Consulta
fuentes institucionales, filtra ayudas con encaje social/no lucrativo y genera
un TXT diario acumulativo junto a un JSON de datos.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "informes_boe_boja_social"
TZ = ZoneInfo("Europe/Madrid")

USER_AGENT = "Mozilla/5.0"

BOE_ARCHIVE_URL = "https://www.boe.es/boe/dias/{year:04d}/{month:02d}/{day:02d}/"
BOJA_FEED_URL = "http://www.juntadeandalucia.es/boja/distribucion/boja.xml"

GRANT_TERMS = [
    "subvencion",
    "subvenciones",
    "ayuda",
    "ayudas",
    "concesion directa de subvenciones",
    "concesión directa de subvenciones",
    "bases reguladoras",
    "convocatoria",
    "convocan",
    "financiacion",
    "financiación",
]

CORE_GRANT_TERMS = [
    "subvencion",
    "subvenciones",
    "ayuda",
    "ayudas",
    "concesion directa de subvenciones",
    "concesión directa de subvenciones",
    "bases reguladoras",
]

NONPROFIT_TERMS = [
    "entidades sin animo de lucro",
    "entidades sin ánimo de lucro",
    "sin animo de lucro",
    "sin ánimo de lucro",
    "entidades sociales",
    "tercer sector",
    "plataforma del tercer sector",
    "asociaciones",
    "asociacion",
    "asociación",
    "fundaciones",
    "fundacion",
    "fundación",
    "ong",
    "organizaciones no gubernamentales",
    "organizaciones de voluntariado",
    "voluntariado",
    "cruz roja",
    "caritas",
    "cáritas",
    "facua",
    "consumidores en accion",
    "consumidores en acción",
    "asociaciones de consumidores",
]

SOCIAL_AREA_TERMS = [
    "accion social",
    "acción social",
    "servicios sociales",
    "inclusion social",
    "inclusión social",
    "exclusion social",
    "exclusión social",
    "pobreza",
    "vulnerabilidad",
    "personas vulnerables",
    "familias vulnerables",
    "infancia",
    "menores",
    "juventud",
    "discapacidad",
    "dependencia",
    "personas mayores",
    "mayores",
    "migrantes",
    "inmigracion",
    "inmigración",
    "igualdad",
    "violencia de genero",
    "violencia de género",
    "cooperacion internacional",
    "cooperación internacional",
    "consumidores y usuarios",
    "personas consumidoras",
]

NEGATIVE_TERMS = [
    "nombramiento",
    "nombramientos",
    "concurso de meritos",
    "concurso de méritos",
    "libre designacion",
    "libre designación",
    "licitacion",
    "licitación",
    "contratacion",
    "contratación",
    "adjudicacion de puesto",
    "adjudicación de puesto",
    "jubilacion",
    "jubilación",
]

LOCAL_ENTITY_ONLY_TERMS = [
    "entidades locales",
    "ayuntamientos",
    "diputaciones",
    "municipios",
]

DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|"
    r"\d{1,2}\s+de\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|octubre|noviembre|diciembre)\s+de\s+\d{4})\b",
    re.I,
)

RELATIVE_DEADLINE_RE = re.compile(
    r"(?:plazo(?:\s+de\s+(?:presentacion|presentación|solicitud|solicitudes))?"
    r"|presentacion de solicitudes|presentación de solicitudes)"
    r".{0,100}?(?:sera|será|es|de)\s+"
    r"((?:\d+|un|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|"
    r"quince|veinte|treinta)\s+(?:dias|días|mes|meses)(?:\s+habiles|\s+hábiles|\s+naturales)?)",
    re.I,
)

OPEN_CONTEXT_RE = re.compile(
    r"(?:apertura|inicio|se inicia|comenzara|comenzará|a partir del|desde el)"
    r".{0,120}",
    re.I,
)

CLOSE_CONTEXT_RE = re.compile(
    r"(?:cierre|finaliza|finalizara|finalizará|hasta el|fecha limite|fecha límite|"
    r"fin de plazo|plazo maximo|plazo máximo).{0,150}",
    re.I,
)


@dataclass
class Notice:
    source: str
    title: str
    url: str
    published_date: str
    entity: str
    section: str
    topic: str
    summary: str
    pdf_url: str = ""


@dataclass
class SocialGrant:
    source: str
    entity: str
    scope: str
    title: str
    published_date: str
    open_date: str
    close_date: str
    url: str
    pdf_url: str
    beneficiary_hint: str
    matched_terms: list[str]
    score: int
    checked_at: str


class LinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[dict[str, str]] = []
        self._href = ""
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        values = dict(attrs)
        href = values.get("href") or ""
        if href:
            self._href = normalize_official_url(urllib.parse.urljoin(self.base_url, href))
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            self.links.append({"url": self._href, "text": clean_text(" ".join(self._text))})
            self._href = ""
            self._text = []


def normalize_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"\s+", " ", value).strip().lower()
    return value


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", value)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_official_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(html.unescape(url.strip()))
    netloc = parsed.netloc.lower()
    scheme = "https" if netloc in {"www.boe.es", "boe.es", "www.juntadeandalucia.es"} else parsed.scheme
    path = re.sub(r"/{2,}", "/", parsed.path)
    return urllib.parse.urlunsplit((scheme or "https", netloc, path, parsed.query, ""))


def fetch_bytes(url: str, timeout: int) -> bytes:
    last_error: Exception | None = None
    for attempt in range(3):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/xml,text/xml,*/*",
                "Connection": "close",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                content_length = response.headers.get("Content-Length")
                if content_length and content_length.isdigit():
                    return response.read(int(content_length))
                chunks: list[bytes] = []
                total = 0
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > 12_000_000:
                        break
                return b"".join(chunks)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
    raise RuntimeError(f"No se pudo consultar {url}: {last_error}")


def decode_payload(payload: bytes) -> str:
    for encoding in ("utf-8", "iso-8859-1", "windows-1252"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


def parse_target_date(value: str | None) -> date:
    if not value:
        return datetime.now(TZ).date()
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_pubdate(value: str) -> str:
    try:
        parsed = parsedate_to_datetime(value)
        return parsed.astimezone(TZ).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        return ""


def has_any(text: str, terms: list[str]) -> bool:
    normalized = normalize_text(text)
    return any(term_present(normalized, term) for term in terms)


def matched_terms(text: str, terms: list[str]) -> list[str]:
    normalized = normalize_text(text)
    found = []
    for term in terms:
        if term_present(normalized, term) and term not in found:
            found.append(term)
    return found


def term_present(normalized_text: str, term: str) -> bool:
    normalized_term = normalize_text(term)
    if not normalized_term:
        return False
    if " " in normalized_term:
        return normalized_term in normalized_text
    pattern = rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])"
    return re.search(pattern, normalized_text) is not None


def first_context(text: str, terms: list[str], width: int = 300) -> str:
    cleaned = clean_text(text)
    normalized = normalize_text(cleaned)
    for term in terms:
        index = normalized.find(normalize_text(term))
        if index < 0:
            continue
        start = max(0, index - width // 3)
        end = min(len(cleaned), index + width)
        return cleaned[start:end].strip(" .,:;")
    return "No detallado en el listado; revisar el enlace oficial."


def extract_entity_from_boe(summary: str) -> str:
    parts = [clean_text(part) for part in summary.split(" - ") if clean_text(part)]
    for part in parts:
        upper = part.upper()
        if upper.startswith(("MINISTERIO", "UNIVERSIDADES", "CONSEJO", "AGENCIA", "COMUNIDAD")):
            return part
    return "Agencia Estatal Boletin Oficial del Estado"


def collect_boe(target: date, timeout: int, errors: list[str]) -> list[Notice]:
    url = BOE_ARCHIVE_URL.format(year=target.year, month=target.month, day=target.day)
    try:
        text = decode_payload(fetch_bytes(url, timeout))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return []
        errors.append(f"BOE: HTTP {exc.code} al consultar {url}")
        return []
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        errors.append(f"BOE: {type(exc).__name__}: {exc}")
        return []

    notices: list[Notice] = []
    pattern = re.compile(r'(?is)<li\s+class="dispo">(.*?)(?=<li\s+class="dispo">|</ul>\s*<h[345]|</div>\s*</div>|$)')
    for match in pattern.finditer(text):
        block = match.group(1)
        title_match = re.search(r"(?is)<p>(.*?)</p>", block)
        link_match = re.search(r'href="([^"]*txt\.php\?id=BOE-[^"]+)"', block)
        if not title_match or not link_match:
            continue
        previous = text[: match.start()]
        section = last_heading(previous, "h3")
        entity = last_heading(previous, "h4") or "Agencia Estatal Boletin Oficial del Estado"
        topic = last_heading(previous, "h5")
        title = clean_text(title_match.group(1))
        doc_url = normalize_official_url(urllib.parse.urljoin(url, link_match.group(1)))
        pdf_match = re.search(r'href="([^"]*BOE-[^"]+\.pdf)"', block)
        pdf_url = normalize_official_url(urllib.parse.urljoin(url, pdf_match.group(1))) if pdf_match else ""
        summary = " - ".join(part for part in [section, entity, topic] if part)
        notices.append(
            Notice(
                source="BOE",
                title=title,
                url=doc_url,
                published_date=target.isoformat(),
                entity=entity,
                section=section,
                topic=topic,
                summary=summary,
                pdf_url=pdf_url,
            )
        )
    return notices


def last_heading(text: str, tag: str) -> str:
    matches = list(re.finditer(fr"(?is)<{tag}[^>]*>(.*?)</{tag}>", text))
    if not matches:
        return ""
    return clean_text(matches[-1].group(1))


def collect_boja(target: date, timeout: int, errors: list[str]) -> list[Notice]:
    try:
        payload = fetch_bytes(BOJA_FEED_URL, timeout)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        errors.append(f"BOJA: {type(exc).__name__}: {exc}")
        return []

    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        errors.append(f"BOJA: XML no valido: {exc}")
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom", "xhtml": "http://www.w3.org/1999/xhtml"}
    notices: list[Notice] = []
    for entry in root.findall("atom:entry", ns):
        updated = (entry.findtext("atom:updated", default="", namespaces=ns) or "")[:10]
        if updated != target.isoformat():
            continue
        bulletin_title = clean_text(entry.findtext("atom:title", default="", namespaces=ns))
        content = entry.find("atom:content", ns)
        if content is None:
            continue
        div = content.find("xhtml:div", ns)
        if div is None:
            continue
        notices.extend(parse_boja_content(div, target, bulletin_title))
    return notices


def parse_boja_content(div: ET.Element, target: date, bulletin_title: str) -> list[Notice]:
    notices: list[Notice] = []
    current_section = ""
    current_topic = ""
    current_entity = "Junta de Andalucia"

    for child in list(div):
        tag = local_name(child.tag)
        text = clean_text(" ".join(child.itertext()))
        if tag == "p":
            if re.match(r"^\d+\.", text) or text.startswith("0."):
                if current_section:
                    current_topic = text
                else:
                    current_section = text
                continue
            if text and not text.lower().startswith("boletin:"):
                current_entity = text
            continue
        if tag != "ul":
            continue
        for li in child:
            links = links_from_xml(li, BOJA_FEED_URL)
            html_link: dict[str, str] | None = None
            pdf_url = ""
            for link in links:
                lower_url = link["url"].lower()
                if lower_url.endswith(".pdf"):
                    pdf_url = link["url"]
                elif re.search(r"/boja/\d{4}/\d+/\d+\.html$", lower_url):
                    html_link = link
            if not html_link:
                continue
            title = clean_text(html_link["text"])
            if not title:
                continue
            summary = " - ".join(part for part in [bulletin_title, current_section, current_topic] if part)
            notices.append(
                Notice(
                    source="BOJA",
                    title=title,
                    url=html_link["url"],
                    published_date=target.isoformat(),
                    entity=current_entity,
                    section=current_section,
                    topic=current_topic,
                    summary=summary,
                    pdf_url=pdf_url,
                )
            )
    return notices


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def links_from_xml(element: ET.Element, base_url: str) -> list[dict[str, str]]:
    links = []
    for node in element.iter():
        if local_name(node.tag) != "a":
            continue
        href = node.attrib.get("href", "")
        if not href:
            continue
        links.append(
            {
                "url": normalize_official_url(urllib.parse.urljoin(base_url, href)),
                "text": clean_text(" ".join(node.itertext())),
            }
        )
    return links


def score_notice(notice: Notice, detail_text: str) -> tuple[int, list[str]]:
    title_summary = f"{notice.title} {notice.summary} {notice.entity}"
    full = f"{title_summary} {detail_text}"
    core_grant_matches = matched_terms(full, CORE_GRANT_TERMS)
    grant_matches = matched_terms(full, GRANT_TERMS)
    nonprofit_matches = matched_terms(full, NONPROFIT_TERMS)
    social_matches = matched_terms(full, SOCIAL_AREA_TERMS)
    negative_matches = matched_terms(title_summary, NEGATIVE_TERMS)

    if not has_any(title_summary, CORE_GRANT_TERMS):
        return 0, []
    if not nonprofit_matches and not social_matches:
        return 0, []

    score = 0
    if has_any(title_summary, CORE_GRANT_TERMS):
        score += 5
    else:
        score += 2
    if nonprofit_matches:
        score += 5
    if social_matches:
        score += 3
    if has_any(title_summary, NONPROFIT_TERMS + SOCIAL_AREA_TERMS):
        score += 2
    if has_any(full, ["plazo", "solicitudes", "beneficiarios", "beneficiarias"]):
        score += 1
    if negative_matches:
        score -= 5

    local_only = has_any(full, LOCAL_ENTITY_ONLY_TERMS)
    if local_only and not nonprofit_matches and score < 11:
        return 0, []

    terms = grant_matches + nonprofit_matches + social_matches
    deduped: list[str] = []
    for term in terms:
        if term not in deduped:
            deduped.append(term)
    return score, deduped[:12]


def likely_candidate(notice: Notice) -> bool:
    haystack = f"{notice.title} {notice.summary} {notice.entity}"
    return has_any(haystack, CORE_GRANT_TERMS + NONPROFIT_TERMS + SOCIAL_AREA_TERMS)


def fetch_detail_text(notice: Notice, timeout: int, errors: list[str]) -> str:
    try:
        text = clean_text(decode_payload(fetch_bytes(notice.url, timeout)))
        if notice.source == "BOE":
            return extract_boe_body(text)
        return text
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        errors.append(f"{notice.source} / detalle {notice.url}: {type(exc).__name__}: {exc}")
        return ""


def extract_boe_body(text: str) -> str:
    markers = ["TEXTO ORIGINAL", "Texto original"]
    for marker in markers:
        if marker in text:
            text = text.split(marker, 1)[1]
            break
    for marker in ["ANALISIS", "Análisis", "Analisis"]:
        if marker in text:
            text = text.split(marker, 1)[0]
    return text.strip()


def extract_open_date(text: str, published_date: str) -> str:
    for context in OPEN_CONTEXT_RE.findall(text):
        found = DATE_RE.search(context)
        if found:
            return found.group(0)
    return f"No publicada expresamente; publicacion oficial: {published_date}"


def extract_close_date(text: str) -> str:
    for context in CLOSE_CONTEXT_RE.findall(text):
        found = DATE_RE.search(context)
        if found:
            return found.group(0)
    relative = RELATIVE_DEADLINE_RE.search(clean_text(text))
    if relative:
        return f"No publicada como fecha cerrada; plazo indicado: {relative.group(1)}"
    return "No publicada expresamente; revisar el texto oficial"


def build_results(notices: list[Notice], timeout: int, errors: list[str]) -> list[SocialGrant]:
    checked_at = datetime.now(TZ).isoformat(timespec="seconds")
    results: list[SocialGrant] = []
    seen: set[str] = set()

    for notice in notices:
        if not likely_candidate(notice):
            continue
        detail = fetch_detail_text(notice, timeout, errors)
        score, terms = score_notice(notice, detail)
        if score < 6:
            continue
        key = hashlib.sha256(f"{notice.source}|{notice.url}".encode("utf-8")).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        combined_text = f"{notice.title}. {notice.summary}. {detail}"
        results.append(
            SocialGrant(
                source=notice.source,
                entity=notice.entity,
                scope="Estatal" if notice.source == "BOE" else "Andalucia",
                title=notice.title,
                published_date=notice.published_date,
                open_date=extract_open_date(combined_text, notice.published_date),
                close_date=extract_close_date(combined_text),
                url=notice.url,
                pdf_url=notice.pdf_url,
                beneficiary_hint=first_context(
                    combined_text,
                    ["beneficiari", "entidades sin", "asociaciones", "fundaciones", "tercer sector", "voluntariado"],
                ),
                matched_terms=terms,
                score=score,
                checked_at=checked_at,
            )
        )
    results.sort(key=lambda item: (-item.score, item.source, item.title.lower()))
    return results


def render_txt(target: date, results: list[SocialGrant], errors: list[str], previous_text: str) -> str:
    now = datetime.now(TZ)
    previous_urls = set(re.findall(r"Enlace oficial:\s*(\S+)", previous_text))
    new_results = [item for item in results if item.url not in previous_urls]

    lines = [
        "REVISION DIARIA BOE/BOJA - SUBVENCIONES PARA ENTIDADES SOCIALES",
        f"Fecha revisada: {target.isoformat()}",
        f"Ejecucion: {now:%Y-%m-%d %H:%M:%S %Z}",
        "Fuentes: BOE y BOJA.",
        "Filtro: subvenciones/ayudas con indicios de entidades sociales, tercer sector, asociaciones, fundaciones, ONG o fines sociales.",
        "",
    ]

    if not new_results:
        if results:
            lines.append("Sin nuevas incorporaciones en este TXT; las coincidencias detectadas ya estaban registradas.")
        elif errors:
            lines.append("Revision incompleta: no se puede confirmar la ausencia de novedades porque hubo incidencias.")
        else:
            lines.append("Sin subvenciones nuevas para entidades sociales localizadas en BOE o BOJA en esta fecha.")
        lines.append("")

    for index, item in enumerate(new_results, 1):
        lines.extend(
            [
                f"{index}. {item.title}",
                f"Entidad convocante: {item.entity}",
                f"Fuente: {item.source}",
                f"Ambito: {item.scope}",
                f"Fecha de publicacion: {item.published_date}",
                f"Fecha de apertura: {item.open_date}",
                f"Fecha de cierre: {item.close_date}",
                f"Beneficiarios/encaje detectado: {item.beneficiary_hint}",
                f"Coincidencias: {', '.join(item.matched_terms)}",
                f"Enlace oficial: {item.url}",
            ]
        )
        if item.pdf_url:
            lines.append(f"PDF oficial: {item.pdf_url}")
        lines.append("")

    lines.append(f"Novedades incorporadas en esta ejecucion: {len(new_results)}")
    lines.append(f"Coincidencias totales para la fecha: {len(results)}")
    if errors:
        lines.append(f"Incidencias: {len(errors)}")
        lines.extend(f"- {error}" for error in errors)
    return "\n".join(lines).rstrip() + "\n"


def render_summary(target: date, results: list[SocialGrant], errors: list[str]) -> str:
    lines = [
        f"# Revision BOE/BOJA - {target.isoformat()}",
        "",
        f"- Coincidencias localizadas: {len(results)}",
        f"- Incidencias: {len(errors)}",
        "",
    ]
    if not results:
        lines.append("No se han localizado subvenciones para entidades sociales en BOE o BOJA para esta fecha.")
    for item in results:
        lines.extend(
            [
                f"## {item.title}",
                "",
                f"- Entidad convocante: {item.entity}",
                f"- Fuente: {item.source}",
                f"- Ambito: {item.scope}",
                f"- Fecha de apertura: {item.open_date}",
                f"- Fecha de cierre: {item.close_date}",
                f"- Enlace oficial: {item.url}",
                "",
            ]
        )
    if errors:
        lines.extend(["## Incidencias", ""])
        lines.extend(f"- {error}" for error in errors)
    return "\n".join(lines).rstrip() + "\n"


def write_outputs(output: Path, target: date, results: list[SocialGrant], errors: list[str]) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    txt_path = output / f"ayudas_sociales_boe_boja_{target.isoformat()}.txt"
    previous_text = txt_path.read_text(encoding="utf-8") if txt_path.exists() else ""
    block = render_txt(target, results, errors, previous_text)
    with txt_path.open("a", encoding="utf-8") as handle:
        if previous_text:
            handle.write("\n" + ("-" * 72) + "\n\n")
        handle.write(block)

    payload = {
        "date": target.isoformat(),
        "checked_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "results": [asdict(item) for item in results],
        "errors": errors,
    }
    (output / f"datos_boe_boja_social_{target.isoformat()}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary = render_summary(target, results, errors)
    (output / "resumen_ultima_revision.md").write_text(summary, encoding="utf-8")
    summary_env = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_env:
        Path(summary_env).write_text(summary, encoding="utf-8")
    return txt_path


def run(target: date, output: Path, timeout: int) -> tuple[list[SocialGrant], list[str], Path]:
    errors: list[str] = []
    notices = []
    notices.extend(collect_boe(target, timeout, errors))
    notices.extend(collect_boja(target, timeout, errors))
    results = build_results(notices, timeout, errors)
    txt_path = write_outputs(output, target, results, errors)
    return results, errors, txt_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scraper diario BOE/BOJA de subvenciones sociales")
    parser.add_argument("--date", help="Fecha a revisar en formato YYYY-MM-DD. Por defecto, hoy en Europe/Madrid.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Carpeta de salida.")
    parser.add_argument("--timeout", type=int, default=25, help="Timeout por consulta en segundos.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target = parse_target_date(args.date)
    results, errors, txt_path = run(target, args.output, args.timeout)
    print(
        f"Revision BOE/BOJA terminada: {len(results)} coincidencias, "
        f"{len(errors)} incidencias. TXT: {txt_path}"
    )
    return 0 if results or not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
