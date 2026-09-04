# Bibliojocs API

API REST (FastAPI + SQLite) para la PWA de Bibliojocs. Sustituye a Firebase
(Firestore + Authentication, proyecto `edubibliojocs`) desde 2026-09.

## Endpoints

- `GET  /api/health`
- `GET  /api/preferences` — favoritos, valoraciones, reportes, resúmenes agregados y flag admin.
- `POST /api/favorites/toggle` `{ game_key }`
- `POST /api/ratings` `{ game_key, value }` (con lógica de toggle 1-5)
- `POST /api/reports` `{ game_key }` (actividad rota)
- `GET  /api/submissions`
- `POST /api/submissions` `{ title, url, notes, area, language, name }`
- `POST /api/admin/login` `{ token }`

Identidad anónima por cookie firmada (HMAC, sin Google). El modo admin se
activa con `POST /api/admin/login` usando `BIBLIOJOCS_ADMIN_TOKEN`.

## Despliegue

Código en `/opt/bibliojocs-api`, servicio systemd `bibliojocs-api.service`
(uvicorn `127.0.0.1:8004`), expuesto en `bibliojocs.edutictac.es/api/`.
Variables de entorno en `/etc/bibliojocs-api.env`:

```
BIBLIOJOCS_SECRET=...
BIBLIOJOCS_ADMIN_TOKEN=...
BIBLIOJOCS_DB=/var/lib/bibliojocs-api/bibliojocs.db
```

El token de admin se guarda en `pass bibliojocs/admin-token`.

## Datos migrados

`seed.json` contiene los datos exportados de Firestore el 2026-09-04:
`ratingSummary` (11), `brokenReports` (28) y `submissions` (1). Se insertan en
la primera inicialización de la base de datos (si la tabla está vacía).

## Licencia

MIT.
