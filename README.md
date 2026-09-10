# Recursos API

API REST (FastAPI + SQLite) para la PWA de Banc de recursos. Sustituye a Firebase
(Firestore + Authentication, proyecto `edubibliojocs`) desde 2026-09.

Usa `edutictac-community` como núcleo común para conexión SQLite, rate limit,
cookies firmadas y cliente OIDC. La lógica propia de Banc de recursos
(favoritos, valoraciones, reportes e índice federado) sigue en este servicio.

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
- `POST /api/student/login` — inicia sesión con credencial pseudónima EduTicTac ID
- `POST /api/student/logout` — cierra sesión de alumnado
- `POST /api/teacher/student-batches` `{ count, pin_length }` — genera credenciales pseudónimas para profesorado autenticado
- `POST /api/admin/resources/hide` `{ game_key }` — oculta un recurso del listado público
- `GET  /api/resources` — índice federado de recursos (búsqueda + filtros)
- `GET  /api/admin/sources` — estado de las fuentes de recursos (requiere admin)

Identidad anónima por cookie firmada (HMAC, sin Google). El modo admin se
activa al iniciar sesión con Authentik si el correo OIDC figura en
`OIDC_ADMIN_EMAILS`. El alumnado puede iniciar sesión con una credencial
pseudónima EduTicTac ID (`public_code + PIN`); el backend solo guarda la sesión
local `student:<codigo>:<identity_id>` para favoritos, valoraciones y reportes.

## Núcleo común

Dependencia estable actual:

```txt
edutictac-community @ git+https://git.edutictac.es/Edutictac/edutictac-community.git@v0.1.1
```

Componentes reutilizados:

- `edutictac_community.db.connect` para SQLite con WAL.
- `edutictac_community.ratelimit.RateLimiter` para límites en memoria.
- `edutictac_community.session.SignedSession` para cookies HMAC.
- `edutictac_community.oidc.OIDCClient` para Authentik/OIDC.

No se usa aún `create_community_router`: los endpoints públicos de la PWA usan
`game_key`, mientras el router común trabaja con `item_key`. Migrarlo requiere
un adaptador o configuración explícita para no romper clientes ni datos.

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
OIDC_ADMIN_SUBS=...
OIDC_ADMIN_EMAILS=...
EDUTICTAC_ID_API_URL=http://127.0.0.1:8005
EDUTICTAC_ID_TEACHER_TOKEN=...
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
