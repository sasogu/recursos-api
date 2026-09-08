"""Tests del proveedor SCORM: detección, parseo de imsmanifest y seguridad del ZIP."""
import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402
from app.providers.scorm import (  # noqa: E402
    ZipValidationError,
    detect_scorm_version,
    find_manifest,
    parse_imsmanifest,
    validate_zip,
)

MANIFEST_1_2 = """<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="MANIFEST-123" version="1.0"
  xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"
  xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2">
  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>1.2</schemaversion>
  </metadata>
  <organizations default="ORG-1">
    <organization identifier="ORG-1">
      <title>Curso de Fracciones</title>
      <item identifier="ITEM-1" identifierref="RES-1">
        <title>Lección 1</title>
      </item>
    </organization>
  </organizations>
  <resources>
    <resource identifier="RES-1" type="webcontent" adlcp:scormtype="sco" href="index.html">
      <file href="index.html" />
    </resource>
  </resources>
</manifest>
""".encode("utf-8")

MANIFEST_2004 = """<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="M-2004" version="1.0"
  xmlns="http://www.imsglobal.org/xsd/imscp_v1p1"
  xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_v1p3">
  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>2004 4th Edition</schemaversion>
  </metadata>
  <organizations default="ORG-1">
    <organization identifier="ORG-1">
      <title>Curso 2004</title>
      <item identifier="ITEM-1" identifierref="RES-1">
        <title>Tema</title>
      </item>
    </organization>
  </organizations>
  <resources>
    <resource identifier="RES-1" type="webcontent" adlcp:scormtype="sco" href="sco.html" />
  </resources>
</manifest>
""".encode("utf-8")

MANIFEST_LOM = """<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="LOM-1"
  xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"
  xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2">
  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>1.2</schemaversion>
    <lom xmlns="http://ltsc.ieee.org/xsd/LOM">
      <general>
        <title><string lang="es">Matemáticas</string></title>
        <language>es</language>
        <description><string lang="es">Actividad de fracciones</string></description>
        <keyword><string>fracciones</string></keyword>
        <keyword><string>primaria</string></keyword>
      </general>
      <lifeCycle>
        <contribute>
          <role><source>LOMv1.0</source><value>author</value></role>
          <entity>BEGIN:VCARD&#10;FN:Samuel Soriano&#10;END:VCARD</entity>
        </contribute>
      </lifeCycle>
    </lom>
  </metadata>
  <organizations default="ORG-1">
    <organization identifier="ORG-1">
      <title>Curso</title>
      <item identifier="ITEM-1" identifierref="RES-1"><title>L1</title></item>
    </organization>
  </organizations>
  <resources>
    <resource identifier="RES-1" type="webcontent" adlcp:scormtype="sco" href="index.html" />
  </resources>
</manifest>
""".encode("utf-8")


def _make_zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_detect_scorm_version_12():
    assert detect_scorm_version(parse_imsmanifest(MANIFEST_1_2)) == "1.2"


def test_detect_scorm_version_2004():
    assert detect_scorm_version(parse_imsmanifest(MANIFEST_2004)) == "2004"


def test_parse_manifest_basic():
    parsed = parse_imsmanifest(MANIFEST_1_2)
    assert parsed["identifier"] == "MANIFEST-123"
    assert parsed["title"] == "Curso de Fracciones"
    assert parsed["schema"] == "ADL SCORM"
    assert parsed["schemaversion"] == "1.2"
    assert parsed["launch_resource"] == "index.html"
    assert len(parsed["items"]) == 1


def test_parse_manifest_lom():
    parsed = parse_imsmanifest(MANIFEST_LOM)
    assert parsed["title"] == "Matemáticas"
    assert parsed["language"] == "es"
    assert parsed["description"] == "Actividad de fracciones"
    assert parsed["keywords"] == ["fracciones", "primaria"]
    assert "Samuel Soriano" in parsed["author"]


def test_parse_manifest_blocks_xxe():
    evil = b"""<?xml version="1.0"?>
<!DOCTYPE manifest [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<manifest identifier="&xxe;" xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2">
  <metadata><schema>ADL SCORM</schema><schemaversion>1.2</schemaversion></metadata>
</manifest>
"""
    # defusedxml lanza error ante DTD/entidades externas.
    import defusedxml
    try:
        parse_imsmanifest(evil)
        raised = False
    except defusedxml.DefusedXmlException:
        raised = True
    assert raised


def test_find_manifest_root_and_subdir():
    zf = zipfile.ZipFile(io.BytesIO(_make_zip({"imsmanifest.xml": MANIFEST_1_2})))
    assert find_manifest(zf) == MANIFEST_1_2

    zf2 = zipfile.ZipFile(io.BytesIO(_make_zip({"paquete/imsmanifest.xml": MANIFEST_1_2})))
    assert find_manifest(zf2) == MANIFEST_1_2


def test_zip_slip_rejected():
    zbytes = _make_zip({"../evil.txt": b"x", "imsmanifest.xml": MANIFEST_1_2})
    try:
        validate_zip(zbytes)
        raised = False
    except ZipValidationError:
        raised = True
    assert raised


def test_zip_absolute_path_rejected():
    zbytes = _make_zip({"/etc/evil.txt": b"x", "imsmanifest.xml": MANIFEST_1_2})
    try:
        validate_zip(zbytes)
        raised = False
    except ZipValidationError:
        raised = True
    assert raised


def test_zip_bomb_limits(monkeypatch):
    monkeypatch.setattr(config, "MAX_ZIP_UNCOMPRESSED", 100)
    # Un archivo de 1 KB comprimido supera el límite descomprimido.
    zbytes = _make_zip({"imsmanifest.xml": MANIFEST_1_2, "big.bin": b"0" * 1024})
    try:
        validate_zip(zbytes)
        raised = False
    except ZipValidationError:
        raised = True
    assert raised


def test_no_manifest_raises():
    zbytes = _make_zip({"otro.txt": b"sin manifest"})
    zf = validate_zip(zbytes)
    try:
        find_manifest(zf)
        raised = False
    except ZipValidationError:
        raised = True
    assert raised
