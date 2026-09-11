from __future__ import annotations

import hashlib
import html
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from html.parser import HTMLParser

from ..extractors import clean_text, enrich_opportunity
from ..models import Opportunity
from ..scoring import MARINE_TERMS, SCIENCE_EDUCATION_TERMS, SOCIAL_TERMS, normalize_text
from .base import BaseSource, SourceContext, fetch_text, host_allowed


FUNDING_TERMS = [
    "subvencion",
    "ayuda",
    "convocatoria",
    "financiacion",
    "grant",
    "funding",
    "call for proposals",
    "premio",
    "patrocinio",
    "fempa",
    "pleamar",
]

RELEVANCE_TERMS = list(MARINE_TERMS) + list(SCIENCE_EDUCATION_TERMS) + list(SOCIAL_TERMS) + [
    "asociaciones",
    "sin ánimo de lucro",
    "voluntariado ambiental",
]


class LinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[tuple[str, str]] = []
        self.page_title = ""
        self._href = ""
        self._text: list[str] = []
        self._in_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "title":
            self._in_title = True
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href") or ""
        if href:
            self._href = urllib.parse.urljoin(self.base_url, html.unescape(href))
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False
            self.page_title = clean_text(" ".join(self._title_parts))
        if tag.lower() == "a" and self._href:
            self.links.append((self._href, clean_text(" ".join(self._text))))
            self._href = ""
            self._text = []


def is_candidate_link(title: str, url: str) -> bool:
    normalized = normalize_text(f"{title} {url}")
    return any(term in normalized for term in FUNDING_TERMS)


def is_relevant(text: str) -> bool:
    normalized = normalize_text(text)
    return any(normalize_text(term) in normalized for term in RELEVANCE_TERMS)


class GenericPageSource(BaseSource):
    def __init__(self, config: dict[str, object]) -> None:
        super().__init__(config)
        self.errors: list[str] = []

    def collect(self, context: SourceContext) -> list[Opportunity]:
        if self.config["adapter"] == "rss":
            return self._collect_rss(context)
        return self._collect_html(context)

    def _collect_html(self, context: SourceContext) -> list[Opportunity]:
        landing_html = fetch_text(self.config["url"], context, self.config)
        parser = LinkParser(self.config["url"])
        parser.feed(landing_html)
        candidates: list[tuple[str, str]] = []
        seen: set[str] = set()
        if self.config.get("include_landing", False) and is_candidate_link(
            parser.page_title or self.name, self.config["url"]
        ):
            candidates.append((self.config["url"], parser.page_title or self.name))
            seen.add(self.config["url"])
        for url, title in parser.links:
            url = urllib.parse.urldefrag(url).url
            if url in seen or not host_allowed(url, list(self.config["official_domains"])):
                continue
            if is_candidate_link(title, url):
                seen.add(url)
                candidates.append((url, title or self.name))
            if len(candidates) >= int(self.config.get("max_items", 20)):
                break

        opportunities: list[Opportunity] = []
        pause = float(self.config.get("rate_limit_seconds", 0.2))
        for url, link_title in candidates:
            try:
                detail_html = landing_html if url == self.config["url"] else fetch_text(url, context, self.config)
            except Exception as exc:
                self.errors.append(f"{url}: {type(exc).__name__}: {exc}")
                continue
            parser = LinkParser(url)
            parser.feed(detail_html)
            title = parser.page_title or link_title
            combined = f"{title} {clean_text(detail_html)}"
            if not is_relevant(combined):
                continue
            opportunity = Opportunity(
                id=hashlib.sha256(url.encode("utf-8")).hexdigest(),
                source_id=self.id,
                title=title,
                organization=self.config.get("organization", self.name),
                source=self.name,
                source_group=self.config["group"],
                organization_type=self.config.get("organization_type", "Organismo público"),
                territory=self.config.get("territory", "Dato no localizado"),
                province=self.config.get("province", "Dato no localizado"),
                municipality=self.config.get("municipality", "Dato no localizado"),
                official_url=url,
                summary=(
                    f"{self.config.get('eligibility_hint', '') if self.config.get('metadata_verified') else ''} "
                    f"{self.config.get('consortium_hint', '') if self.config.get('metadata_verified') else ''} "
                    f"{clean_text(detail_html)[:1_000]}"
                ).strip(),
                checked_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                coverage_type=str(self.config.get("coverage_type", "current")),
                coverage_note=str(self.config.get("coverage_note", "")),
                metadata_verified=bool(self.config.get("metadata_verified", False)),
            )
            opportunities.append(enrich_opportunity(opportunity, detail_html, context.today))
            if pause:
                time.sleep(min(pause, 2.0))
        return opportunities

    def _collect_rss(self, context: SourceContext) -> list[Opportunity]:
        xml_text = fetch_text(self.config["url"], context, self.config)
        root = ET.fromstring(xml_text)
        opportunities: list[Opportunity] = []
        for entry in list(root.iter("item")) + list(root.iter("{http://www.w3.org/2005/Atom}entry")):
            title = clean_text(
                entry.findtext("title")
                or entry.findtext("{http://www.w3.org/2005/Atom}title")
                or "Convocatoria sin título"
            )
            link = entry.findtext("link") or ""
            atom_link = entry.find("{http://www.w3.org/2005/Atom}link")
            if not link and atom_link is not None:
                link = atom_link.attrib.get("href", "")
            summary = clean_text(
                entry.findtext("description")
                or entry.findtext("{http://www.w3.org/2005/Atom}summary")
                or ""
            )
            if not link or not host_allowed(link, list(self.config["official_domains"])):
                continue
            if not is_candidate_link(title, link) or not is_relevant(f"{title} {summary}"):
                continue
            opportunities.append(
                Opportunity(
                    id=hashlib.sha256(link.encode("utf-8")).hexdigest(),
                    source_id=self.id,
                    title=title,
                    organization=self.config.get("organization", self.name),
                    source=self.name,
                    source_group=self.config["group"],
                    organization_type=self.config.get("organization_type", "Organismo público"),
                    territory=self.config.get("territory", "Dato no localizado"),
                    province=self.config.get("province", "Dato no localizado"),
                    municipality=self.config.get("municipality", "Dato no localizado"),
                    official_url=link,
                    summary=(
                        f"{self.config.get('eligibility_hint', '') if self.config.get('metadata_verified') else ''} "
                        f"{self.config.get('consortium_hint', '') if self.config.get('metadata_verified') else ''} "
                        f"{summary}"
                    ).strip(),
                    raw_text=summary,
                    checked_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                    coverage_type=str(self.config.get("coverage_type", "rss")),
                    coverage_note=str(self.config.get("coverage_note", "")),
                    metadata_verified=bool(self.config.get("metadata_verified", False)),
                )
            )
        return opportunities[: int(self.config.get("max_items", 20))]
