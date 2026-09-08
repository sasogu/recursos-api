"""Proveedor SCORM: ingesta de paquetes por URL y parseo seguro de imsmanifest.xml.

NO hay repositorio central de SCORM; se trata como formato que aparece en
distintas fuentes. Este proveedor descarga el ZIP a memoria, localiza
imsmanifest.xml, detecta SCORM 1.2 / 2004 y extrae metadatos SIN ejecutar nada.

Seguridad: sin extracción a disco, sin entidades XML externas (defusedxml),
límites de tamaño/nº de archivos/profundidad y rechazo de rutas maliciosas.
"""
from __future__ import annotations

import io
import json
import zipfile
from typing import Iterator

from defusedxml import ElementTree as DET

from .. import config
from ..httpclient import get_bytes
from ..models import Resource
from ..taxonomy import language_codes
from .base import ResourceProvider

_SCHEMAVERSION_1_2 = "1.2"
_SCHEMAVERSION_2004 = ("2004", "1.3")


class ZipValidationError(ValueError):
    pass


def validate_zip(zip_bytes: bytes) -> zipfile.ZipFile:
    """Abre un ZIP en memoria aplicando límites de seguridad (zip slip, bombs...)."""
    if len(zip_bytes) > config.MAX_ZIP_SIZE:
        raise ZipValidationError(f"ZIP excesivo: {len(zip_bytes)} bytes")

    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    total_uncompressed = 0
    count = 0
    for info in zf.infolist():
        name = info.filename
        if name.startswith("/") or name.startswith("\\") or ".." in name.replace("\\", "/").split("/"):
            raise ZipValidationError(f"ruta maliciosa en ZIP: {name!r}")
        if name.count("/") > config.MAX_ZIP_DEPTH:
            raise ZipValidationError(f"profundidad excesiva en ZIP: {name!r}")
        total_uncompressed += info.file_size
        count += 1
        if count > config.MAX_ZIP_FILES:
            raise ZipValidationError("demasiados archivos en ZIP")
        if total_uncompressed > config.MAX_ZIP_UNCOMPRESSED:
            raise ZipValidationError("ZIP descomprimido excesivo (posible zip bomb)")
    return zf


def find_manifest(zf: zipfile.ZipFile) -> bytes:
    """Localiza y devuelve el contenido de imsmanifest.xml (raíz o subdirectorio)."""
    candidates = [n for n in zf.namelist() if n.lower().rstrip("/").endswith("imsmanifest.xml")]
    if not candidates:
        raise ZipValidationError("no se encontró imsmanifest.xml")
    # Preferir el de la raíz (menos profundo).
    candidates.sort(key=lambda n: n.count("/"))
    return zf.read(candidates[0])


def _local_text(elem, local_name: str) -> str:
    for child in elem.iter():
        if _local(child) == local_name:
            return "".join(child.itertext()).strip()
    return ""


def _local(elem) -> str:
    tag = elem.tag
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def parse_imsmanifest(xml_bytes: bytes) -> dict:
    """Parseo seguro de imsmanifest.xml (sin XXE). Devuelve metadatos normalizados."""
    root = DET.fromstring(xml_bytes)

    schema = _local_text(root, "schema")
    schemaversion = _local_text(root, "schemaversion")

    title = _local_text(root, "title")
    identifier = root.get("identifier", "")

    # Metadatos LOM embebidos (general / lifeCycle / educational / rights).
    language = ""
    description = ""
    keywords = []
    author = ""
    for lom in root.iter():
        if _local(lom) != "lom":
            continue
        for general in lom:
            if _local(general) != "general":
                continue
            for field in general:
                ln = _local(field)
                if ln == "title" and not title:
                    title = _local_text(field, "string")
                elif ln == "language":
                    language = _local_text(field, "string") or field.text or ""
                elif ln == "description":
                    description = _local_text(field, "string")
                elif ln == "keyword":
                    keywords.append(_local_text(field, "string"))
            break
        for lifecycle in lom:
            if _local(lifecycle) != "lifeCycle":
                continue
            for contribute in lifecycle:
                if _local(contribute) != "contribute":
                    continue
                for field in contribute:
                    if _local(field) == "entity" and not author:
                        author = "".join(field.itertext()).strip()
            break
        break

    # Organizaciones / items / launch resource.
    items = []
    launch_resource = ""
    for resource in root.iter():
        if _local(resource) == "resource":
            href = resource.get("href", "")
            scormtype = (resource.get("{http://www.adlnet.org/xsd/adlcp_v1p3}scormtype")
                         or resource.get("{http://www.adlnet.org/xsd/adlcp_rootv1p2}scormtype")
                         or resource.get("scormtype") or "")
            identifierref = resource.get("identifier", "")
            if scormtype.lower() == "sco" and not launch_resource:
                launch_resource = href
            items.append({"identifier": identifierref, "href": href, "scormtype": scormtype})

    return {
        "title": title or identifier,
        "description": description,
        "identifier": identifier,
        "version": root.get("version", ""),
        "language": language,
        "author": author,
        "organization": _local_text(root, "organization"),
        "items": items,
        "launch_resource": launch_resource,
        "keywords": keywords,
        "schema": schema,
        "schemaversion": schemaversion,
    }


def detect_scorm_version(parsed: dict) -> str | None:
    sv = (parsed.get("schemaversion") or "").strip().lower()
    if "2004" in sv or sv.startswith("1.3"):
        return "2004"
    if "1.2" in sv:
        return "1.2"
    schema = (parsed.get("schema") or "").strip().lower()
    if "2004" in schema:
        return "2004"
    return None


class SCORMProvider(ResourceProvider):
    name = "scorm"
    format = "scorm"

    def __init__(self, sources_path: str | None = None) -> None:
        self.sources_path = sources_path

    def discover(self) -> Iterator[Resource]:
        path = self.sources_path
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                sources = json.load(f)
        except FileNotFoundError:
            return
        except (ValueError, OSError) as exc:
            raise ValueError(f"scorm-sources.json inválido: {exc}") from exc
        for entry in sources or []:
            url = entry if isinstance(entry, str) else entry.get("url", "")
            if not url:
                continue
            yield self.ingest_from_url(url)

    def ingest(self, url: str) -> Resource:
        return self.ingest_from_url(url)

    def ingest_from_url(self, url: str) -> Resource:
        zip_bytes = get_bytes(url)
        zf = validate_zip(zip_bytes)
        manifest = find_manifest(zf)
        parsed = parse_imsmanifest(manifest)
        return self.normalize({"url": url, "manifest": parsed})

    def normalize(self, raw: dict) -> Resource:
        manifest = raw.get("manifest", {})
        url = raw.get("url", "")
        version = detect_scorm_version(manifest)
        external_id = manifest.get("identifier") or url
        language = manifest.get("language") or ""
        author = manifest.get("author") or ""

        return Resource(
            provider=self.name,
            external_id=str(external_id),
            title=manifest.get("title") or "",
            description=manifest.get("description") or "",
            author=author,
            license="",
            license_known=False,
            language=language_codes([language]),
            resource_type="scorm",
            format=self.format,
            subject="",
            educational_stage="",
            educational_level=[],
            tags=manifest.get("keywords", []),
            source_url=url,
            play_url=url,
            download_url=url,
            thumbnail_url="",
            metadata_json={
                "url": url,
                "manifest": manifest,
                "scorm_version": version,
            },
            created_at_source="",
            updated_at_source="",
        )
