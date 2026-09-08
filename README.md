# Recursos API

API REST (FastAPI + SQLite) para la PWA de Banc de recursos. Sustituye a Firebase
(Firestore + Authentication, proyecto `edubibliojocs`) desde 2026-09.

## Endpoints

- `GET  /api/health`
- `GET  /api/preferences` — favoritos, valoraciones, reportes, resúmenes agregados y flag admin.
- `POST /api/favorites/toggle` `{ game_key }`
- `POST /api/ratings` `{ game_key, value }` (con lógica de toggle 1-5)
- `POST /api/reports` `{ game_key }` (actividad rota)
- `GET  /api/submissions`
- `POST /api/submissions` `{ title, url, notes, area, language, name }`
- `GET  /api/auth/login` — inicia sesión con Authentik
- `GET  /api/auth/logout` — cierra sesión local
- `GET  /api/auth/me` — estado de sesión OIDC
- `GET  /api/resources` — índice federado de recursos (búsqueda + filtros)
- `GET  /api/admin/sources` — estado de las fuentes de recursos (requiere admin)

Identidad anónima por cookie firmada (HMAC, sin Google). El modo admin se
activa al iniciar sesión con Authentik si el correo OIDC figura en
`OIDC_ADMIN_EMAILS`.

## Despliegue

Código en `/opt/recursos-api`, servicio systemd `recursos-api.service`
(uvicorn `127.0.0.1:8004`), expuesto en `recursos.edutictac.es/api/`.
Variables de entorno en `/etc/recursos-api.env`:

```
RECURSOS_SECRET=...
RECURSOS_DB=/var/lib/recursos-api/recursos.db
OIDC_ISSUER=https://id.edutictac.es/application/o/<slug>/
OIDC_CLIENT_ID=...
OIDC_CLIENT_SECRET=...
OIDC_REDIRECT_URI=https://recursos.edutictac.es/api/auth/callback
OIDC_SCOPE=openid
OIDC_ADMIN_EMAILS=...
```

Los secretos de OIDC y sesión se guardan fuera del repositorio, en el fichero de
entorno del servicio.

## Datos migrados

`seed.json` contiene los datos exportados de Firestore el 2026-09-04:
`ratingSummary` (11), `brokenReports` (28) y `submissions` (1). Se insertan en
la primera inicialización de la base de datos (si la tabla está vacía).

## Licencia

GNU Affero General Public License v3.0 (AGPL-3.0).

## Índice federado de recursos (en desarrollo)

Además de favoritos/valoraciones, este backend aloja el **índice federado de
recursos educativos abiertos** que alimentará `recursos.edutictac.es`.

- Proveedores: `jclic`, `h5p`, `scorm`, `eduhoot` (paquete `app/providers/`).
- Modelo común `Resource` + `SyncRun` (SQLite, tablas `resources` y `sync_runs`).
- CLI de sincronización:

```bash
python -m app.cli sync jclic|h5p|scorm|eduhoot|all
python -m app.cli sync scorm --url https://.../paquete.zip
python -m app.cli stats
python -m app.cli sources
```

- Búsqueda unificada en `GET /api/resources` con filtros (`q`, `provider`,
  `format`, `subject`, `stage`, `language`, `license`, `license_known`).
- Documentación completa y fuentes verificadas: ver
  `docs/resource-indexers.md` en el repositorio del frontend (`sasogu/recursos`).

Tests: `python -m pytest tests/` (requiere `httpx`, `defusedxml`, `pytest`).
