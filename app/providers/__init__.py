"""Registro de proveedores disponibles."""
from __future__ import annotations

from .base import ResourceProvider
from .jclic import JClicProvider
from .h5p import H5POERHubProvider
from .scorm import SCORMProvider
from .eduhoot import EduHootProvider


def get_providers() -> dict[str, ResourceProvider]:
    return {
        p.name: p
        for p in (
            JClicProvider(),
            H5POERHubProvider(),
            SCORMProvider(),
            EduHootProvider(),
        )
    }


def get_provider(name: str) -> ResourceProvider:
    providers = get_providers()
    if name not in providers:
        raise KeyError(f"provider desconocido: {name}. Disponibles: {sorted(providers)}")
    return providers[name]
