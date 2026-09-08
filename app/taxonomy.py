"""Taxonomía educativa EduTicTac y capas de mapeo desde fuentes externas.

Mantiene la clasificación original (en metadata_json) y añade una clasificación
normalizada. Los valores canónicos coinciden con los que usa el frontend
(scripts/i18n.js y data/games.json).
"""
from __future__ import annotations

# Valores canónicos del frontend.
STAGES = ["Infantil", "Primaria", "Secundaria"]
LEVELS = [
    "Infantil",
    "Primaria",
    "Primaria 1er ciclo",
    "Primaria 2o ciclo",
    "Primaria 3er ciclo",
    "Secundaria",
]
AREAS = [
    "Artes",
    "Ciencias Naturales",
    "Ciencias Sociales",
    "Conocimiento del Medio",
    "Dias especiales",
    "Diversas áreas",
    "Educacion Fisica",
    "Educacion emocional",
    "Frances",
    "General",
    "Informatica",
    "Ingles",
    "Juegos",
    "Lengua",
    "Logica",
    "Manualitats",
    "Matematicas",
    "Musica",
    "Religion",
    "Seguridad Digital",
    "Tecnología",
]
LANGUAGES = ["Aranes", "Castellano", "Català/Valencià", "Ingles", "Frances"]


def normalize_tag(value: str) -> str:
    """Limpia un tag libre: minúsculas, sin tildes, guiones → espacios."""
    import re
    import unicodedata

    s = unicodedata.normalize("NFD", value or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower().replace("-", " ").replace("_", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


# --- Mapeo JClic (projects.json) ---

JCLIC_LANG = {
    "ca": "Català/Valencià",
    "es": "Castellano",
    "en": "Ingles",
    "fr": "Frances",
    "oc": "Aranes",
}

JCLIC_LEVEL = {
    "INF": "Infantil",
    "PRI": "Primaria",
    "SEC": "Secundaria",
    "BTX": "Secundaria",  # bachillerato, sin categoría propia en el frontend
}

JCLIC_AREA = {
    "soc": "Ciencias Sociales",
    "tec": "Tecnología",
    "lleng": "Lengua",
    "div": "Diversas áreas",
    "mat": "Matematicas",
    "exp": "Ciencias Naturales",
    "mus": "Musica",
    "ef": "Educacion Fisica",
    "vip": "General",
}

JCLIC_STAGE = {
    "INF": "Infantil",
    "PRI": "Primaria",
    "SEC": "Secundaria",
    "BTX": "Secundaria",
}


# --- Mapeo de tags EduHoot (tags libres, multilingües) ---

EDUHOOT_AREA_TAGS: dict[str, str] = {
    "musica": "Musica",
    "instrumentos": "Musica",
    "cantantes": "Musica",
    "cuento musical": "Musica",
    "matematicas": "Matematicas",
    "funciones": "Matematicas",
    "cuerpos geometricos": "Matematicas",
    "espanol": "Lengua",
    "catalan": "Lengua",
    "valencia": "Lengua",
    "lengua": "Lengua",
    "lengua castellana": "Lengua",
    "lenguaje": "Lengua",
    "literatura": "Lengua",
    "comunicacion": "Lengua",
    "ingles": "Ingles",
    "angles": "Ingles",
    "vocabulary": "Ingles",
    "historia": "Ciencias Sociales",
    "geografia": "Ciencias Sociales",
    "geografia de europa": "Ciencias Sociales",
    "edad media": "Ciencias Sociales",
    "filosofia": "Ciencias Sociales",
    "actualidad": "Ciencias Sociales",
    "biologia": "Ciencias Naturales",
    "geologia": "Ciencias Naturales",
    "quimica": "Ciencias Naturales",
    "essers vius": "Ciencias Naturales",
    "animals": "Ciencias Naturales",
    "invertebrats": "Ciencias Naturales",
    "informatica": "Informatica",
    "hardware": "Informatica",
    "ordenador": "Informatica",
    "componentes": "Informatica",
    "internos": "Informatica",
    "digitalitzacio basica": "Informatica",
    "programari lliure": "Informatica",
    "sw libre": "Informatica",
    "lliurex": "Informatica",
    "blender": "Informatica",
    "diseno 3d": "Informatica",
    "igualdad de genero": "Educacion emocional",
    "coeducacion": "Educacion emocional",
    "actualidad": "General",
}

EDUHOOT_STAGE_TAGS: dict[str, str] = {
    "infantil": "Infantil",
    "primaria": "Primaria",
    "eso": "Secundaria",
    "batxillerat": "Secundaria",
    "batchillerato": "Secundaria",
    "bachillerato": "Secundaria",
    "secundaria": "Secundaria",
}

# Cursos concretos que indican primaria (conservados como tags, mapeados a etapa).
EDUHOOT_PRIMARY_COURSE_TAGS = {
    "primero", "segundo", "tercero", "cuarto", "quinto", "sexto",
    "1r prim", "2n prim", "3r prim", "4t prim", "5e prim", "6e prim",
    "6 primaria", "sexto primaria",
}


def jclic_language(codes: list[str]) -> list[str]:
    result = []
    for code in codes or []:
        mapped = JCLIC_LANG.get(code, "")
        if mapped and mapped not in result:
            result.append(mapped)
    return result


def jclic_levels(codes: list[str]) -> list[str]:
    result = []
    for code in codes or []:
        mapped = JCLIC_LEVEL.get(code)
        if mapped and mapped not in result:
            result.append(mapped)
    return result


def jclic_stage(codes: list[str]) -> str:
    for code in codes or []:
        stage = JCLIC_STAGE.get(code)
        if stage:
            return stage
    return ""


def jclic_subject(codes: list[str]) -> str:
    for code in codes or []:
        area = JCLIC_AREA.get(code)
        if area and area != "Diversas áreas":
            return area
    return "Diversas áreas"


def eduhoot_subject(tags: list[str]) -> str:
    seen = []
    for raw in tags or []:
        norm = normalize_tag(raw)
        area = EDUHOOT_AREA_TAGS.get(norm)
        if area and area not in seen:
            seen.append(area)
    if not seen:
        return "General"
    return seen[0]


def eduhoot_stage(tags: list[str]) -> str:
    for raw in tags or []:
        norm = normalize_tag(raw)
        if norm in EDUHOOT_STAGE_TAGS:
            return EDUHOOT_STAGE_TAGS[norm]
        if norm in EDUHOOT_PRIMARY_COURSE_TAGS:
            return "Primaria"
        if norm.startswith("1") and ("eso" in norm or "batx" in norm):
            return "Secundaria"
    return ""


def eduhoot_levels(tags: list[str]) -> list[str]:
    stage = eduhoot_stage(tags)
    if not stage:
        return []
    return [stage]


EDUHOOT_LANG = {
    "catala": "Català/Valencià",
    "valencia": "Català/Valencià",
    "valenciano": "Català/Valencià",
    "catalan": "Català/Valencià",
    "ca": "Català/Valencià",
    "castellano": "Castellano",
    "espanol": "Castellano",
    "es": "Castellano",
    "ingles": "Ingles",
    "english": "Ingles",
    "en": "Ingles",
    "frances": "Frances",
    "french": "Frances",
    "fr": "Frances",
    "aranes": "Aranes",
    "oc": "Aranes",
}


def eduhoot_language(raw: str) -> list[str]:
    """Normaliza el idioma declarado por un quiz de EduHoot (string libre)."""
    if not raw:
        return []
    norm = normalize_tag(raw)
    mapped = EDUHOOT_LANG.get(norm)
    if mapped:
        return [mapped]
    return [str(raw).strip()]
