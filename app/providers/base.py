"""Abstracción común de proveedor de recursos."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator

from ..models import Resource


class ResourceProvider(ABC):
    """Contrato para fuentes externas (JClic, H5P, SCORM, EduHoot, ...).

    Un proveedor produce `Resource` normalizados a partir de su fuente. La
    lógica de deduplicación/upsert y el registro SyncRun viven en `sync.py`.

    Modos de ingesta:
      - pull: `discover()` itera los elementos de la fuente (sync incremental).
      - push: `ingest(...)` recibe un paquete/URL concreto (p. ej. SCORM local).
    """

    name: str = "base"
    format: str = ""

    @abstractmethod
    def discover(self) -> Iterator[Resource]:
        """Itera los recursos de la fuente (ya normalizados)."""
        raise NotImplementedError

    @abstractmethod
    def normalize(self, raw: dict) -> Resource:
        """Normaliza un elemento crudo de la fuente a Resource."""
        raise NotImplementedError

    def ingest(self, *args, **kwargs) -> Resource:
        """Ingesta push de un paquete/URL concreto (opcional, por defecto no soportado)."""
        raise NotImplementedError(f"{self.name} no soporta ingesta push")
