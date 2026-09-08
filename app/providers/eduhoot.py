"""Proveedor EduHoot: indexa los quizzes públicos para jugarlos en modo individual.

Fuente: GET /api/public-quizzes (eduhoot.edutictac.es). Sin paginación; devuelve
todos los quizzes públicos (visibility == 'public'). El modo individual se juega
en /solo/?id=<quizId>.

Limitaciones documentadas: los quizzes no declaran idioma ni licencia; los tags
son libres y multilingües (se conservan y se mapean de forma heurística). La
coverImage a veces es un data-URI (se conserva en metadata, no se usa como thumbnail).
"""
from __future__ import annotations

from typing import Iterator

from .. import config, taxonomy
from ..httpclient import get_json
from ..models import Resource
from .base import ResourceProvider


class EduHootProvider(ResourceProvider):
    name = "eduhoot"
    format = "eduhoot"

    def discover(self) -> Iterator[Resource]:
        data = get_json(f"{config.EDUHOOT_BASE_URL}/api/public-quizzes")
        if not isinstance(data, list):
            raise ValueError("public-quizzes no es una lista")
        for raw in data:
            if not self._is_educational(raw):
                continue
            yield self.normalize(raw)

    def _is_educational(self, raw: dict) -> bool:
        """Descarta quizzes de ocio/cultura pop (tags o nombres en blocklist)."""
        name = taxonomy.normalize_tag(raw.get("name", "") or "")
        for fragment in taxonomy.EDUHOOT_NON_EDUCATIONAL_NAME_FRAGMENTS:
            if fragment in name:
                return False
        for tag in raw.get("tags", []) or []:
            if taxonomy.normalize_tag(tag) in taxonomy.EDUHOOT_NON_EDUCATIONAL_TAGS:
                return False
        return True

    def normalize(self, raw: dict) -> Resource:
        quiz_id = raw.get("id", "")
        name = raw.get("name", "")
        tags = raw.get("tags", []) or []
        cover = raw.get("coverImage", "") or ""
        solo_url = f"{config.EDUHOOT_BASE_URL}/solo/?id={quiz_id}"

        thumbnail = cover if isinstance(cover, str) and cover.startswith("http") else ""
        language_raw = raw.get("language", "") or ""
        license_raw = raw.get("license", "") or ""

        return Resource(
            provider=self.name,
            external_id=str(quiz_id),
            title=name,
            description=raw.get("description", "") or "",
            author=raw.get("ownerNickname", "") or "",
            license=license_raw,
            license_known=bool(license_raw),
            language=taxonomy.eduhoot_language(language_raw),
            resource_type="quiz",
            format=self.format,
            subject=taxonomy.eduhoot_subject(tags),
            educational_stage=taxonomy.eduhoot_stage(tags),
            educational_level=taxonomy.eduhoot_levels(tags),
            tags=list(tags),
            source_url=solo_url,
            play_url=solo_url,
            thumbnail_url=thumbnail,
            metadata_json=dict(raw),
            created_at_source=raw.get("createdAt", "") or "",
            updated_at_source=raw.get("updatedAt", "") or "",
        )
