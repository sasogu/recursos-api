"""Tests de la capa de taxonomía (mapeos JClic y EduHoot)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import taxonomy  # noqa: E402


def test_jclic_language_maps_known_codes():
    assert taxonomy.jclic_language(["ca", "es"]) == ["Català/Valencià", "Castellano"]
    assert taxonomy.jclic_language(["en"]) == ["Ingles"]
    assert taxonomy.jclic_language(["oc"]) == ["Aranes"]


def test_jclic_language_ignores_unknown():
    # Códigos no mapeados no deben inventar etiquetas.
    assert taxonomy.jclic_language(["gl", "eu"]) == []


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
    assert taxonomy.eduhoot_language("català") == ["Català/Valencià"]
    assert taxonomy.eduhoot_language("castellano") == ["Castellano"]
    assert taxonomy.eduhoot_language("ingles") == ["Ingles"]
    assert taxonomy.eduhoot_language("francés") == ["Frances"]
    assert taxonomy.eduhoot_language("") == []
    # Idioma no reconocido: se conserva tal cual (no se inventa).
    assert taxonomy.eduhoot_language("gallego") == ["gallego"]
