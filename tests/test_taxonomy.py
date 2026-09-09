"""Tests de la capa de taxonomía (mapeos JClic y EduHoot)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import taxonomy  # noqa: E402


def test_jclic_language_maps_known_codes():
    assert taxonomy.jclic_language(["ca", "es"]) == ["ca", "es"]
    assert taxonomy.jclic_language(["en"]) == ["en"]
    assert taxonomy.jclic_language(["oc"]) == ["oc"]


def test_jclic_language_keeps_any_iso_code():
    # Vocabulario abierto: cualquier código ISO de 2-3 letras se conserva.
    assert taxonomy.jclic_language(["gl", "eu"]) == ["gl", "eu"]
    assert taxonomy.jclic_language(["la", "ar"]) == ["la", "ar"]
    assert taxonomy.jclic_language(["eo"]) == ["eo"]
    assert taxonomy.jclic_language([]) == []
    assert taxonomy.jclic_language(["123"]) == []  # no alfabético se descarta


def test_jclic_levels():
    assert taxonomy.jclic_levels(["INF"]) == ["Infantil"]
    assert taxonomy.jclic_levels(["PRI"]) == ["Primaria"]
    assert taxonomy.jclic_levels(["SEC"]) == ["Secundaria"]
    assert taxonomy.jclic_levels(["BTX"]) == ["Secundaria"]  # bachillerato → secundaria


def test_jclic_subject_skips_diversas():
    assert taxonomy.jclic_subject(["mat"]) == "Matematicas"
    assert taxonomy.jclic_subject(["div"]) == "Diversas áreas"


def test_jclic_stage():
    assert taxonomy.jclic_stage(["INF"]) == "Infantil"
    assert taxonomy.jclic_stage([]) == ""


def test_normalize_tag():
    assert taxonomy.normalize_tag("Música") == "musica"
    assert taxonomy.normalize_tag("Lengua-Castellana") == "lengua castellana"
    assert taxonomy.normalize_tag("3r prim") == "3r prim"


def test_eduhoot_subject():
    assert taxonomy.eduhoot_subject(["musica", "primaria"]) == "Musica"
    assert taxonomy.eduhoot_subject(["lengua-castellana"]) == "Lengua"
    assert taxonomy.eduhoot_subject(["angles"]) == "Ingles"
    assert taxonomy.eduhoot_subject(["historia"]) == "Ciencias Sociales"
    assert taxonomy.eduhoot_subject(["biologia"]) == "Ciencias Naturales"
    assert taxonomy.eduhoot_subject(["fortnite"]) == "General"


def test_eduhoot_stage():
    assert taxonomy.eduhoot_stage(["primaria", "cuarto"]) == "Primaria"
    assert taxonomy.eduhoot_stage(["1r-eso"]) == "Secundaria"
    assert taxonomy.eduhoot_stage(["infantil"]) == "Infantil"
    assert taxonomy.eduhoot_stage(["sexto"]) == "Primaria"
    assert taxonomy.eduhoot_stage(["fortnite"]) == ""


def test_eduhoot_language():
    assert taxonomy.eduhoot_language("català") == ["ca"]
    assert taxonomy.eduhoot_language("castellano") == ["es"]
    assert taxonomy.eduhoot_language("ingles") == ["en"]
    assert taxonomy.eduhoot_language("francés") == ["fr"]
    assert taxonomy.eduhoot_language("") == []
    # Idioma no reconocido: se descarta (vocabulario cerrado a códigos ISO).
    assert taxonomy.eduhoot_language("gallego") == []


def test_language_codes_normalizes_mixed_values():
    assert taxonomy.language_codes(["Castellano", "es"]) == ["es"]
    assert taxonomy.language_codes(["Català/Valencià", "Inglés", "Ingles"]) == ["ca", "en"]
    assert taxonomy.language_codes(["", "ru", None]) == ["ru"]  # vocabulario abierto conserva códigos


def test_language_codes_eu_and_regional_variants():
    assert taxonomy.language_codes(["de"]) == ["de"]
    assert taxonomy.language_codes(["pt-br"]) == ["pt"]
    assert taxonomy.language_codes(["es-mx"]) == ["es"]
    assert taxonomy.language_codes(["en-gb"]) == ["en"]
    # Vocabulario abierto: también conserva códigos fuera de la UE.
    assert taxonomy.language_codes(["ru"]) == ["ru"]
    assert taxonomy.language_codes(["zh-tw"]) == ["zh"]
    assert taxonomy.language_codes(["gl", "eu", "la"]) == ["gl", "eu", "la"]
