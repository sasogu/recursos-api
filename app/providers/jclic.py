"""Proveedor JClic: indexa el catálogo oficial (clic.xtec.cat/projects/projects.json).

Fuente estructurada, sin scraping. Cada proyecto tiene title, author, date,
langCodes, levelCodes, areaCodes, mainFile, cover/thumbnail.
"""
from __future__ import annotations

from typing import Iterator
from urllib.parse import quote

from .. import config, taxonomy
from ..httpclient import get_json
from ..models import Resource
from .base import ResourceProvider

JCLIC_BASE = "https://clic.xtec.cat"


class JClicProvider(ResourceProvider):
    name = "jclic"
    format = "jclic"

    def discover(self) -> Iterator[Resource]:
        data = get_json(config.JCLIC_PROJECTS_URL)
        if not isinstance(data, list):
            raise ValueError("projects.json no es una lista")
        for raw in data:
            yield self.normalize(raw)

    def normalize(self, raw: dict) -> Resource:
        path = raw.get("path", "")
        project_id = raw.get("id", path)
        title = raw.get("title", "")
        author = raw.get("author", "")
        date = raw.get("date", "")
        lang_codes = raw.get("langCodes", [])
        level_codes = raw.get("levelCodes", [])
        area_codes = raw.get("areaCodes", [])
        main_file = raw.get("mainFile", "")

        # Proyecto remoto (clic.xtec.cat) reproducido por el visor local.
        project_url = f"{JCLIC_BASE}/projects/{path}/{main_file}" if path and main_file else ""
        play_url = (
            f"{config.APP_BASE_URL}/jclic.html"
            f"?project={quote(project_url)}&title={quote(title)}"
            if project_url
            else ""
        )
        cover = raw.get("coverWebp") or raw.get("cover") or raw.get("thumbnail") or ""
        thumbnail = f"{JCLIC_BASE}/projects/{path}/{cover}" if path and cover else ""

        language = taxonomy.jclic_language(lang_codes)
        levels = taxonomy.jclic_levels(level_codes)

        return Resource(
            provider=self.name,
            external_id=str(project_id),
            title=title,
            author=author,
            language=language,
            resource_type="jclic",
            format=self.format,
            subject=taxonomy.jclic_subject(area_codes),
            educational_stage=taxonomy.jclic_stage(level_codes),
            educational_level=levels,
            tags=[taxonomy.normalize_tag(title)] if title else [],
            source_url=f"{JCLIC_BASE}/projects/{path}/" if path else "",
            play_url=play_url,
            thumbnail_url=thumbnail,
            metadata_json=dict(raw),
            created_at_source=date,
            license="",
            license_known=False,
        )
