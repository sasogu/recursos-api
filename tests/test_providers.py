"""Tests de filtrado de calidad de los proveedores (H5P y EduHoot)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.providers.eduhoot import EduHootProvider  # noqa: E402
from app.providers.h5p import H5POERHubProvider, _age_is_school, _parse_age  # noqa: E402


def test_parse_age():
    assert _parse_age("12-16") == (12, 16)
    assert _parse_age("11-") == (11, None)
    assert _parse_age("14") == (14, 14)
    assert _parse_age("") == (None, None)
    assert _parse_age("preschool") == (None, None)


def test_age_is_school():
    assert _age_is_school("4-7") is True
    assert _age_is_school("8-11") is True
    assert _age_is_school("12-16") is True
    assert _age_is_school("12-18") is True
    assert _age_is_school("10") is True
    assert _age_is_school("11-") is True
    # Adulto/universitario → fuera del banco.
    assert _age_is_school("18-99") is False
    assert _age_is_school("20-40") is False
    assert _age_is_school("25-65") is False
    assert _age_is_school("18") is False
    assert _age_is_school("") is False


def test_h5p_eligibility_language_and_stage():
    p = H5POERHubProvider()
    assert p._is_eligible({"language": "es", "age": "12-16"}) is True
    assert p._is_eligible({"language": "es-mx", "age": "8-11"}) is True
    assert p._is_eligible({"language": "ca", "age": "6-8"}) is True
    assert p._is_eligible({"language": "en", "age": "12-16"}) is True
    assert p._is_eligible({"language": "fr", "age": "8-11"}) is True
    # Idioma no apto (ruso/alemán) o etapa adulta.
    assert p._is_eligible({"language": "ru", "age": "12-16"}) is False
    assert p._is_eligible({"language": "de", "age": "12-16"}) is False
    assert p._is_eligible({"language": "es", "age": "18-99"}) is False
    assert p._is_eligible({"language": "es", "age": ""}) is False


def test_eduhoot_non_educational_blocked():
    p = EduHootProvider()
    assert p._is_educational({"name": "Minecraft", "tags": ["minecraft", "generado-ia"]}) is False
    assert p._is_educational({"name": "Aitana", "tags": ["espanol", "actualidad"]}) is False
    assert p._is_educational({"name": "Spiderman", "tags": ["peliculas-y-actores"]}) is False
    assert p._is_educational({"name": "Hang the DJ (Black Mirror)", "tags": []}) is False
    assert p._is_educational({"name": "Ready Player One", "tags": []}) is False
    assert p._is_educational({"name": "Roblox", "tags": ["primaria", "valencia"]}) is False
    assert p._is_educational({"name": "Clash Royale", "tags": ["espanol"]}) is False
    assert p._is_educational({"name": "Marvel", "tags": ["espanol"]}) is False


def test_eduhoot_educational_kept():
    p = EduHootProvider()
    assert p._is_educational({"name": "Nombre de las notas musicales", "tags": ["musica", "primaria"]}) is True
    assert p._is_educational({"name": "Números enteros", "tags": ["2-eso", "matematicas"]}) is True
    assert p._is_educational({"name": "Divisions", "tags": []}) is True
