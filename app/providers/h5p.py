"""Proveedor H5P OER Hub (hub-api.h5p.org).

Endpoint público NO documentado oficialmente: /v1/contents devuelve metadatos
completos (título, licencia, disciplinas, nivel, icono, preview, descargas).
Paginación con `from` + `size`; filtros `search`, `text`, `disciplines[]`.
"""
from __future__ import annotations

from typing import Iterator

from .. import config
from ..httpclient import get_json
from ..models import Resource
from .base import ResourceProvider

PAGE_SIZE = 50
H5P_PREVIEW_BASE = "https://hub-api.h5p.org"


class H5POERHubProvider(ResourceProvider):
    name = "h5p"
    format = "h5p"

    def __init__(self, max_items: int | None = None) -> None:
        # max_items permite limitar el número de recursos en pruebas/sync manual.
        self.max_items = max_items

    def discover(self) -> Iterator[Resource]:
        fetched = 0
        offset = 0
        total: int | None = None
        while True:
            data = get_json(
                f"{config.H5P_HUB_API}/contents",
                params={"from": offset, "size": PAGE_SIZE},
            )
            if total is None and isinstance(data, dict):
                total = int(data.get("total", 0) or 0)
            items = data.get("items", []) if isinstance(data, dict) else []
            if not items:
                break
            for raw in items:
                yield self.normalize(raw)
                fetched += 1
                if self.max_items is not None and fetched >= self.max_items:
                    return
            offset += len(items)
            if total is not None and offset >= total:
                break

    def normalize(self, raw: dict) -> Resource:
        hub_id = raw.get("id", "")
        title = raw.get("title", "")
        license_info = raw.get("license") or {}
        publisher = raw.get("publisher") or {}
        disciplines = raw.get("disciplines", []) or []
        language = raw.get("language", "") or ""

        subject = _map_discipline(disciplines)
        stage = _map_level(raw.get("level", "") or "", raw.get("age", "") or "")

        return Resource(
            provider=self.name,
            external_id=str(hub_id),
            title=title,
            description=raw.get("description", "") or raw.get("summary", "") or "",
            author=publisher.get("name", "") or raw.get("owner", ""),
            license=license_info.get("id", "") or "",
            license_known=bool(license_info.get("id")),
            language=[language] if language else [],
            resource_type=raw.get("contentType", "") or raw.get("content_type", ""),
            format=self.format,
            subject=subject,
            educational_stage=stage,
            educational_level=[stage] if stage else [],
            tags=list(disciplines),
            source_url=f"{H5P_PREVIEW_BASE}/content/{hub_id}",
            play_url=raw.get("preview_url", "") or f"{H5P_PREVIEW_BASE}/content/{hub_id}/preview",
            download_url=f"{config.H5P_HUB_API}/contents/{hub_id}/export",
            thumbnail_url=raw.get("icon", "") or "",
            metadata_json=dict(raw),
            created_at_source="",
            updated_at_source=raw.get("updated_at", "") or "",
        )


def _map_discipline(disciplines: list[str]) -> str:
    """Mapea disciplinas OER Hub → área EduTicTac (heurístico)."""
    text = " ".join(disciplines).lower()
    if any(k in text for k in ("math", "mathematics", "geometry", "algebra")):
        return "Matematicas"
    if any(k in text for k in ("language", "linguist", "literature", "english", "spanish", "grammar")):
        return "Lengua"
    if any(k in text for k in ("biology", "chemistry", "physics", "science", "earth")):
        return "Ciencias Naturales"
    if any(k in text for k in ("history", "geograph", "social", "civic", "politic", "econom")):
        return "Ciencias Sociales"
    if any(k in text for k in ("music", "art", "visual", "theatre", "dance")):
        return "Musica"
    if any(k in text for k in ("computer", "program", "coding", "information")):
        return "Informatica"
    if any(k in text for k in ("physical education", "health-and-physical", "sport")):
        return "Educacion Fisica"
    return "General"


def _map_level(level: str, age: str) -> str:
    age = (age or "").lower()
    level = (level or "").lower()
    if any(k in age for k in ("0-6", "3-6", "4-6", "preschool", "kindergarten")):
        return "Infantil"
    if "beginner" in level or any(k in age for k in ("6-", "7-", "8-", "9-", "10-", "11-")):
        return "Primaria"
    if "intermediate" in level or "advanced" in level or any(k in age for k in ("12-", "13-", "14-", "15-", "16-", "17-", "18")):
        return "Secundaria"
    return ""
