"""Proveedor H5P OER Hub (hub-api.h5p.org).

Endpoint público NO documentado oficialmente: /v1/contents devuelve metadatos
completos (título, licencia, disciplinas, nivel, icono, preview, descargas).
Paginación con `from` + `size`; filtros `search`, `text`, `disciplines[]`.

Filtro de calidad: se indexan los recursos en idiomas de la UE (+ catalán/valenciano
y aranés) y con edad escolar o sin edad declarada. Se descartan los idiomas fuera
del vocabulario (ruso, chino, turco...) y el contenido claramente adulto (edad
mínima ≥ 18).
"""
from __future__ import annotations

import re
from typing import Iterator

from .. import config, taxonomy
from ..httpclient import get_json
from ..models import Resource
from .base import ResourceProvider

PAGE_SIZE = 50
H5P_PREVIEW_BASE = "https://hub-api.h5p.org"

# Edad mínima a partir de la cual un recurso se considera contenido adulto.
ADULT_AGE = 18


def _parse_age(age: str) -> tuple[int | None, int | None]:
    """Interpreta el campo `age` del hub: 'N', 'N-M' o 'N-'. Devuelve (min, max)."""
    age = (age or "").strip()
    if not age:
        return None, None
    m = re.fullmatch(r"(\d+)\s*-\s*(\d*)", age)
    if m:
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else None
        return lo, hi
    if age.isdigit():
        n = int(age)
        return n, n
    return None, None


def _age_is_eligible(age: str) -> bool:
    """Acepta recursos sin edad o no-adultos; descarta los claramente adultos."""
    lo, _ = _parse_age(age)
    if lo is None:
        return True
    return lo < ADULT_AGE


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
                if not self._is_eligible(raw):
                    continue
                yield self.normalize(raw)
                fetched += 1
                if self.max_items is not None and fetched >= self.max_items:
                    return
            offset += len(items)
            if total is not None and offset >= total:
                break

    def _is_eligible(self, raw: dict) -> bool:
        """Filtra por idioma (UE + ca/oc) y descarta contenido claramente adulto."""
        language = raw.get("language", "") or ""
        if not taxonomy.language_codes([language]):
            return False
        return _age_is_eligible(raw.get("age", "") or "")

    def normalize(self, raw: dict) -> Resource:
        hub_id = raw.get("id", "")
        title = raw.get("title", "")
        license_info = raw.get("license") or {}
        publisher = raw.get("publisher") or {}
        disciplines = raw.get("disciplines", []) or []
        language = raw.get("language", "") or ""

        subject = _map_discipline(disciplines)
        stage = _map_level(raw.get("age", "") or "")

        return Resource(
            provider=self.name,
            external_id=str(hub_id),
            title=title,
            description=raw.get("description", "") or raw.get("summary", "") or "",
            author=publisher.get("name", "") or raw.get("owner", ""),
            license=license_info.get("id", "") or "",
            license_known=bool(license_info.get("id")),
            language=taxonomy.language_codes([language]),
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


def _map_level(age: str) -> str:
    """Etapa educativa a partir del rango de edad escolar."""
    lo, hi = _parse_age(age)
    if lo is None:
        return ""
    hi = hi if hi is not None else lo
    if hi <= 6:
        return "Infantil"
    if lo >= 12:
        return "Secundaria"
    return "Primaria"
