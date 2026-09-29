"""Crawlable public job-detail pages and XML sitemap."""

import html
import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from datetime import UTC, datetime
from html.parser import HTMLParser
from math import ceil
from typing import Annotated, Any, cast
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.responses import Response as RawResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.core.config import Settings
from app.domains.job_postings.enums import EmploymentType
from app.services.public_jobs import (
    PublicJobPageDetail,
    count_public_job_sitemap_entries,
    get_public_job_page_detail,
    list_public_job_sitemap_entries,
)

router = APIRouter(tags=["Public job pages"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]

_PAGE_CACHE_CONTROL = "public, max-age=60, stale-while-revalidate=300"
_SITEMAP_CACHE_CONTROL = "public, max-age=300, stale-while-revalidate=600"
_SITEMAP_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"
_SITEMAP_PAGE_SIZE = 40_000
_EMPLOYMENT_TYPE = {
    EmploymentType.FULL_TIME: "FULL_TIME",
    EmploymentType.PART_TIME: "PART_TIME",
    EmploymentType.CONTRACT: "CONTRACTOR",
    EmploymentType.TEMPORARY: "TEMPORARY",
    EmploymentType.INTERNSHIP: "INTERN",
}


class _PlainTextDescription(HTMLParser):
    """Extract safe, readable text from a possibly marked-up description."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._hidden_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        if tag.casefold() in {"script", "style"}:
            self._hidden_depth += 1
        elif tag.casefold() in {"br", "p", "div", "li"}:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"script", "style"} and self._hidden_depth:
            self._hidden_depth -= 1
        elif tag.casefold() in {"p", "div", "li"}:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth:
            self.parts.append(data)


def _plain_description(description: str) -> str:
    parser = _PlainTextDescription()
    parser.feed(description)
    parser.close()
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def _iso_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def canonical_job_url(base_url: str, public_id: UUID, slug: str) -> str:
    """Build a canonical URL from configured origin and opaque posting ID."""
    return f"{base_url.rstrip('/')}/jobs/{public_id}/{quote(slug, safe='-')}"


def build_job_posting_json_ld(
    detail: PublicJobPageDetail,
    *,
    canonical_url: str,
    country_code: str,
) -> dict[str, Any] | None:
    """Build Google-compatible JobPosting data when required fields exist."""
    posting = detail.posting
    description = _plain_description(posting.description or "")
    location = (posting.location or "").strip()

    # Google requires a substantive description and a location for a physical
    # role. Do not misrepresent missing data as remote work or invent an address.
    if (
        not posting.published_at
        or not description
        or not location
        or not detail.employer_name.strip()
    ):
        return None

    data: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": posting.title,
        "description": description,
        "datePosted": _iso_datetime(posting.published_at),
        "employmentType": _EMPLOYMENT_TYPE[posting.employment_type],
        "hiringOrganization": {
            "@type": "Organization",
            "name": detail.employer_name,
        },
        "jobLocation": {
            "@type": "Place",
            "address": {
                "@type": "PostalAddress",
                "addressLocality": location,
                "addressCountry": country_code,
            },
        },
        "identifier": {
            "@type": "PropertyValue",
            "name": detail.employer_name,
            "value": str(posting.public_id),
        },
        "url": canonical_url,
    }
    if posting.expires_at is not None:
        data["validThrough"] = _iso_datetime(posting.expires_at)
    return data


def _safe_script_json(data: Mapping[str, Any]) -> str:
    """Serialize JSON-LD without allowing content to terminate its script tag."""
    return (
        json.dumps(data, ensure_ascii=True, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def _render_job_page(
    detail: PublicJobPageDetail,
    *,
    canonical_url: str,
    country_code: str,
) -> str:
    posting = detail.posting
    description = _plain_description(posting.description or "")
    structured_data = build_job_posting_json_ld(
        detail,
        canonical_url=canonical_url,
        country_code=country_code,
    )
    json_ld_tag = (
        f'<script type="application/ld+json">{_safe_script_json(structured_data)}</script>'
        if structured_data is not None
        else ""
    )
    description_meta = _plain_description(description)
    description_tag = (
        f'<meta name="description" content="{html.escape(description_meta, quote=True)}">'
        if description_meta
        else ""
    )
    location = html.escape(posting.location or "")
    department = html.escape(posting.department or "")
    return (
        "<!doctype html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(posting.title)} — {html.escape(detail.employer_name)}</title>"
        f'{description_tag}<link rel="canonical" href="{html.escape(canonical_url, quote=True)}">'
        f"{json_ld_tag}</head><body>"
        f"<main><article><h1>{html.escape(posting.title)}</h1>"
        f"<p>{html.escape(detail.employer_name)}</p>"
        f"<p>{location}</p><p>{department}</p>"
        f'<section class="job-description" style="white-space: pre-wrap">'
        f"{html.escape(description)}</section></article></main>"
        "</body></html>"
    )


def _sitemap_xml(urls: list[tuple[str, datetime]]) -> bytes:
    root = ET.Element(f"{{{_SITEMAP_NAMESPACE}}}urlset")
    for url, updated_at in urls:
        url_element = ET.SubElement(root, f"{{{_SITEMAP_NAMESPACE}}}url")
        ET.SubElement(url_element, f"{{{_SITEMAP_NAMESPACE}}}loc").text = url
        lastmod = updated_at
        if lastmod.tzinfo is None:
            lastmod = lastmod.replace(tzinfo=UTC)
        ET.SubElement(url_element, f"{{{_SITEMAP_NAMESPACE}}}lastmod").text = (
            lastmod.astimezone(UTC).date().isoformat()
        )
    return cast(bytes, ET.tostring(root, encoding="utf-8", xml_declaration=True))


def _sitemap_index_xml(urls: list[str]) -> bytes:
    root = ET.Element(f"{{{_SITEMAP_NAMESPACE}}}sitemapindex")
    for url in urls:
        sitemap = ET.SubElement(root, f"{{{_SITEMAP_NAMESPACE}}}sitemap")
        ET.SubElement(sitemap, f"{{{_SITEMAP_NAMESPACE}}}loc").text = url
    return cast(bytes, ET.tostring(root, encoding="utf-8", xml_declaration=True))


@router.get("/jobs/{public_id}/{slug}", include_in_schema=False)
async def public_job_page(
    public_id: UUID,
    slug: str,
    request: Request,
    session: DatabaseSession,
) -> Response:
    """Serve crawlable HTML and structured data for a visible public job."""
    settings: Settings = request.app.state.settings
    detail = await get_public_job_page_detail(session, public_id=public_id)
    canonical_url = canonical_job_url(
        str(settings.public_site_base_url),
        public_id,
        detail.posting.slug,
    )
    if slug != detail.posting.slug:
        return RedirectResponse(
            canonical_url,
            status_code=301,
            headers={"Cache-Control": _PAGE_CACHE_CONTROL},
        )

    return HTMLResponse(
        content=_render_job_page(
            detail,
            canonical_url=canonical_url,
            country_code=settings.public_job_country_code,
        ),
        headers={"Cache-Control": _PAGE_CACHE_CONTROL},
    )


@router.get("/sitemap.xml", include_in_schema=False)
async def public_job_sitemap(
    request: Request,
    session: DatabaseSession,
) -> Response:
    """Return a sitemap containing only currently visible job-detail pages."""
    base_url = str(request.app.state.settings.public_site_base_url)
    total = await count_public_job_sitemap_entries(session)
    page_count = max(1, ceil(total / _SITEMAP_PAGE_SIZE))
    if page_count > 1:
        sitemap = _sitemap_index_xml(
            [f"{base_url.rstrip('/')}/sitemap/jobs/{page}.xml" for page in range(1, page_count + 1)]
        )
    else:
        entries = await list_public_job_sitemap_entries(
            session,
            offset=0,
            limit=_SITEMAP_PAGE_SIZE,
        )
        sitemap = _sitemap_xml(
            [
                (
                    canonical_job_url(base_url, entry.public_id, entry.slug),
                    entry.updated_at,
                )
                for entry in entries
            ]
        )
    return RawResponse(
        content=sitemap,
        media_type="application/xml",
        headers={"Cache-Control": _SITEMAP_CACHE_CONTROL},
    )


@router.get("/sitemap/jobs/{page}.xml", include_in_schema=False)
async def public_job_sitemap_page(
    page: int,
    request: Request,
    session: DatabaseSession,
) -> Response:
    """Return one bounded shard when published jobs exceed one sitemap."""
    if page < 1:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    total = await count_public_job_sitemap_entries(session)
    page_count = max(1, ceil(total / _SITEMAP_PAGE_SIZE))
    if page > page_count:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    base_url = str(request.app.state.settings.public_site_base_url)
    entries = await list_public_job_sitemap_entries(
        session,
        offset=(page - 1) * _SITEMAP_PAGE_SIZE,
        limit=_SITEMAP_PAGE_SIZE,
    )
    sitemap = _sitemap_xml(
        [
            (
                canonical_job_url(base_url, entry.public_id, entry.slug),
                entry.updated_at,
            )
            for entry in entries
        ]
    )
    return RawResponse(
        content=sitemap,
        media_type="application/xml",
        headers={"Cache-Control": _SITEMAP_CACHE_CONTROL},
    )


@router.get("/robots.txt", include_in_schema=False)
async def public_robots_txt(request: Request) -> Response:
    """Advertise the canonical sitemap to crawlers without exposing API URLs."""
    base_url = str(request.app.state.settings.public_site_base_url).rstrip("/")
    api_prefix = request.app.state.settings.api_prefix.rstrip("/")
    content = (
        "User-agent: *\n"
        "Allow: /jobs/\n"
        f"Disallow: {api_prefix}/\n"
        f"Sitemap: {base_url}/sitemap.xml\n"
    )
    return RawResponse(
        content=content,
        media_type="text/plain",
        headers={"Cache-Control": _SITEMAP_CACHE_CONTROL},
    )
