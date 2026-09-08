"""Bibliojocs API — backend autoalojado que sustituye a Firebase Firestore+Auth.

API REST (FastAPI + SQLite) para la PWA de Bibliojocs: favoritos, valoraciones
(con resumen agregado), avisos de actividad rota, propuestas de actividades y
modo admin por token. Identidad anónima por cookie firmada (sin Google).

Endpoints:
  GET  /api/health
  GET  /api/preferences
  POST /api/favorites/toggle   { game_key }
  POST /api/ratings            { game_key, value }
  POST /api/reports            { game_key }
  GET  /api/submissions
  POST /api/submissions        { title, url, notes, area, language, name? }
  GET  /api/auth/login
  GET  /api/auth/callback
  GET  /api/auth/logout
  GET  /api/auth/me
  POST /api/admin/resources/hide { game_key }
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app import oidc
from app.db import init_index_schema
from app.models import Resource

DB_PATH = os.environ.get("RECURSOS_DB", "/var/lib/recursos-api/recursos.db")
SESSION_SECRET = os.environ.get("RECURSOS_SECRET", "")
SESSION_COOKIE = "recursos_session"
COOKIE_SECURE = os.environ.get("RECURSOS_COOKIE_SECURE", "1").lower() not in {"0", "false", "no"}

RATE_WINDOW = 60
RATE_MAX = 60
_rate_lock = threading.Lock()
_rate: dict[str, deque] = defaultdict(deque)

app = FastAPI(title="Bibliojocs API")
logger = logging.getLogger("recursos_api")


def _ensure_dir() -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)


def get_conn() -> sqlite3.Connection:
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS rating_summary (
                game_key TEXT PRIMARY KEY,
                sum INTEGER NOT NULL DEFAULT 0,
                count INTEGER NOT NULL DEFAULT 0,
                avg REAL NOT NULL DEFAULT 0,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS broken_reports (
                game_key TEXT PRIMARY KEY,
                count INTEGER NOT NULL DEFAULT 0,
                admin_reported INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS submissions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                notes TEXT DEFAULT '',
                area TEXT DEFAULT 'General',
                language TEXT DEFAULT '',
                submitted_by TEXT DEFAULT '',
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS favorites (
                user_id TEXT NOT NULL,
                game_key TEXT NOT NULL,
                created_at TEXT,
                PRIMARY KEY (user_id, game_key)
            );
            CREATE TABLE IF NOT EXISTS ratings (
                user_id TEXT NOT NULL,
                game_key TEXT NOT NULL,
                value INTEGER NOT NULL,
                updated_at TEXT,
                PRIMARY KEY (user_id, game_key)
            );
            CREATE TABLE IF NOT EXISTS reports (
                user_id TEXT NOT NULL,
                game_key TEXT NOT NULL,
                reported_at TEXT,
                PRIMARY KEY (user_id, game_key)
            );
            """
        )
        _seed(conn)


def _seed(conn: sqlite3.Connection) -> None:
    seed_path = Path(__file__).with_name("seed.json")
    if not seed_path.exists():
        return
    data = json.loads(seed_path.read_text(encoding="utf-8"))

    for row in data.get("rating_summary", []):
        conn.execute(
            "INSERT OR IGNORE INTO rating_summary (game_key, sum, count, avg) VALUES (?, ?, ?, ?)",
            (row["game_key"], row.get("sum", 0), row.get("count", 0), row.get("avg", 0)),
        )
    for row in data.get("broken_reports", []):
        conn.execute(
            "INSERT OR IGNORE INTO broken_reports (game_key, count, admin_reported) VALUES (?, ?, ?)",
            (row["game_key"], row.get("count", 0), 1 if row.get("admin_reported") else 0),
        )
    for row in data.get("submissions", []):
        conn.execute(
            "INSERT OR IGNORE INTO submissions (id, title, url, notes, area, language, submitted_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                row["id"],
                row.get("title", ""),
                row.get("url", ""),
                row.get("notes", ""),
                row.get("area", "General"),
                row.get("language", ""),
                row.get("submitted_by", ""),
            ),
        )


init_db()
init_index_schema()


# --- Sesión firmada (cookie) ---

def _sign(data: str) -> str:
    if not SESSION_SECRET:
        raise RuntimeError("RECURSOS_SECRET is required")
    return hmac.new(SESSION_SECRET.encode(), data.encode(), hashlib.sha256).hexdigest()


def make_session(uid: str, admin: bool = False) -> str:
    payload = json.dumps({"uid": uid, "admin": bool(admin)})
    data = base64.urlsafe_b64encode(payload.encode()).decode()
    return f"{data}.{_sign(data)}"


def parse_session(cookie: str | None) -> dict | None:
    if not cookie or not SESSION_SECRET:
        return None
    try:
        data, sig = cookie.split(".", 1)
        expected = _sign(data)
        if not hmac.compare_digest(sig, expected):
            return None
        return json.loads(base64.urlsafe_b64decode(data.encode()).decode())
    except Exception:
        return None


def set_session_cookie(response: Response, value: str, max_age: int) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        value,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
        max_age=max_age,
    )


def delete_session_cookie(response: Response) -> None:
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=COOKIE_SECURE,
        samesite="lax",
    )


def describe_oidc_error(exc: Exception) -> str:
    parts = [exc.__class__.__name__]
    for attr in ("error", "description"):
        value = getattr(exc, attr, None)
        if value:
            parts.append(f"{attr}={str(value)[:160]}")
    message = str(exc)
    if message and "code=" not in message and "state=" not in message:
        parts.append(f"message={message[:160]}")
    return " ".join(parts)


def session_admin(uid: str, cookie_admin: bool) -> bool:
    if uid.startswith("oidc:") and oidc.is_admin_sub(uid[len("oidc:"):]):
        return True
    return cookie_admin


def get_session(request: Request) -> tuple[str, bool]:
    """Devuelve (uid, admin). Crea identidad anónima si no hay cookie válida."""
    cookie = request.cookies.get(SESSION_COOKIE)
    sess = parse_session(cookie)
    if sess and sess.get("uid"):
        uid = sess["uid"]
        return uid, session_admin(uid, bool(sess.get("admin")))
    return "", False


def rate_limited(ip: str) -> bool:
    now = time.monotonic()
    with _rate_lock:
        q = _rate[ip]
        while q and now - q[0] > RATE_WINDOW:
            q.popleft()
        if len(q) >= RATE_MAX:
            return True
        q.append(now)
    return False


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


# --- Modelos ---

class GameKeyIn(BaseModel):
    game_key: str


class RatingIn(BaseModel):
    game_key: str
    value: int


class SubmissionIn(BaseModel):
    title: str
    url: str
    notes: str = ""
    area: str = "General"
    language: str = ""
    name: str = ""


# --- Endpoints ---

@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/preferences")
def preferences(request: Request) -> dict:
    uid, admin = get_session(request)
    with get_conn() as conn:
        favorites = [r["game_key"] for r in conn.execute(
            "SELECT game_key FROM favorites WHERE user_id = ?", (uid,)
        )] if uid else []
        ratings = {r["game_key"]: r["value"] for r in conn.execute(
            "SELECT game_key, value FROM ratings WHERE user_id = ?", (uid,)
        )} if uid else {}
        reports = [r["game_key"] for r in conn.execute(
            "SELECT game_key FROM reports WHERE user_id = ?", (uid,)
        )] if uid else []
        rating_summary = {
            r["game_key"]: {"avg": r["avg"], "count": r["count"]}
            for r in conn.execute("SELECT game_key, avg, count FROM rating_summary")
        }
        broken_reports = {
            r["game_key"]: {"count": r["count"], "admin_reported": bool(r["admin_reported"])}
            for r in conn.execute("SELECT game_key, count, admin_reported FROM broken_reports")
        }
    return {
        "admin": admin,
        "favorites": favorites,
        "ratings": ratings,
        "reports": reports,
        "rating_summary": rating_summary,
        "broken_reports": broken_reports,
    }


@app.post("/api/favorites/toggle")
def toggle_favorite(payload: GameKeyIn, request: Request, response: Response) -> dict:
    if rate_limited(_client_ip(request)):
        raise HTTPException(status_code=429, detail="too many requests")
    uid, _ = _ensure_uid(request, response)
    game_key = payload.game_key.strip()
    if not game_key:
        raise HTTPException(status_code=400, detail="invalid game_key")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM favorites WHERE user_id = ? AND game_key = ?", (uid, game_key)
        ).fetchone()
        if row:
            conn.execute("DELETE FROM favorites WHERE user_id = ? AND game_key = ?", (uid, game_key))
            return {"favorite": False}
        conn.execute(
            "INSERT INTO favorites (user_id, game_key, created_at) VALUES (?, ?, ?)",
            (uid, game_key, datetime.now(timezone.utc).isoformat()),
        )
        return {"favorite": True}


@app.post("/api/ratings")
def set_rating(payload: RatingIn, request: Request, response: Response) -> dict:
    if rate_limited(_client_ip(request)):
        raise HTTPException(status_code=429, detail="too many requests")
    uid, _ = _ensure_uid(request, response)
    game_key = payload.game_key.strip()
    if not game_key:
        raise HTTPException(status_code=400, detail="invalid game_key")
    value = max(0, min(5, payload.value))

    with get_conn() as conn:
        current_row = conn.execute(
            "SELECT value FROM ratings WHERE user_id = ? AND game_key = ?", (uid, game_key)
        ).fetchone()
        current = current_row["value"] if current_row else 0
        next_val = 0 if current == value else value

        summary = conn.execute(
            "SELECT sum, count FROM rating_summary WHERE game_key = ?", (game_key,)
        ).fetchone()
        s = summary["sum"] if summary else 0
        c = summary["count"] if summary else 0

        if current > 0:
            s -= current
            c -= 1
        if next_val > 0:
            s += next_val
            c += 1
            conn.execute(
                "INSERT INTO ratings (user_id, game_key, value, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(user_id, game_key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (uid, game_key, next_val, datetime.now(timezone.utc).isoformat()),
            )
        else:
            conn.execute("DELETE FROM ratings WHERE user_id = ? AND game_key = ?", (uid, game_key))

        if c <= 0:
            conn.execute("DELETE FROM rating_summary WHERE game_key = ?", (game_key,))
            avg, count = 0.0, 0
        else:
            avg = round(s / c, 2)
            conn.execute(
                "INSERT INTO rating_summary (game_key, sum, count, avg, updated_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(game_key) DO UPDATE SET sum=excluded.sum, count=excluded.count, avg=excluded.avg, updated_at=excluded.updated_at",
                (game_key, s, c, avg, datetime.now(timezone.utc).isoformat()),
            )
            count = c

    return {"value": next_val, "avg": avg, "count": count}


@app.post("/api/reports")
def report_broken(payload: GameKeyIn, request: Request, response: Response) -> dict:
    if rate_limited(_client_ip(request)):
        raise HTTPException(status_code=429, detail="too many requests")
    uid, admin = _ensure_uid(request, response)
    game_key = payload.game_key.strip()
    if not game_key:
        raise HTTPException(status_code=400, detail="invalid game_key")

    with get_conn() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO reports (user_id, game_key, reported_at) VALUES (?, ?, ?)",
            (uid, game_key, datetime.now(timezone.utc).isoformat()),
        )
        inserted_report = cur.rowcount > 0
        row = conn.execute(
            "SELECT count, admin_reported FROM broken_reports WHERE game_key = ?", (game_key,)
        ).fetchone()
        count = (row["count"] if row else 0) + (1 if inserted_report else 0)
        admin_reported = bool(row["admin_reported"]) if row else False
        if admin:
            admin_reported = True
        conn.execute(
            "INSERT INTO broken_reports (game_key, count, admin_reported, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(game_key) DO UPDATE SET count=excluded.count, admin_reported=excluded.admin_reported, updated_at=excluded.updated_at",
            (game_key, count, 1 if admin_reported else 0, datetime.now(timezone.utc).isoformat()),
        )
    return {"count": count, "admin_reported": admin_reported}


@app.post("/api/admin/resources/hide")
def admin_hide_resource(payload: GameKeyIn, request: Request, response: Response) -> dict:
    if rate_limited(_client_ip(request)):
        raise HTTPException(status_code=429, detail="too many requests")
    _, admin = _ensure_uid(request, response)
    if not admin:
        raise HTTPException(status_code=403, detail="admin required")
    game_key = payload.game_key.strip()
    if not game_key:
        raise HTTPException(status_code=400, detail="invalid game_key")

    with get_conn() as conn:
        row = conn.execute(
            "SELECT count FROM broken_reports WHERE game_key = ?", (game_key,)
        ).fetchone()
        count = row["count"] if row else 0
        conn.execute(
            "INSERT INTO broken_reports (game_key, count, admin_reported, updated_at) VALUES (?, ?, 1, ?) "
            "ON CONFLICT(game_key) DO UPDATE SET admin_reported=1, updated_at=excluded.updated_at",
            (game_key, count, datetime.now(timezone.utc).isoformat()),
        )
    return {"game_key": game_key, "count": count, "admin_reported": True}


@app.get("/api/submissions")
def list_submissions() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM submissions ORDER BY created_at DESC").fetchall()
    return [
        {
            "id": r["id"],
            "title": r["title"],
            "url": r["url"],
            "notes": r["notes"],
            "area": r["area"],
            "language": r["language"],
            "submitted_by": r["submitted_by"],
        }
        for r in rows
    ]


@app.post("/api/submissions", status_code=201)
def add_submission(payload: SubmissionIn, request: Request, response: Response) -> dict:
    if rate_limited(_client_ip(request)):
        raise HTTPException(status_code=429, detail="too many requests")
    uid, _ = _ensure_uid(request, response)
    title = payload.title.strip()
    url = payload.url.strip()
    if not title or not url:
        raise HTTPException(status_code=400, detail="title and url required")

    sub_id = secrets.token_urlsafe(10)
    created_at = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO submissions (id, title, url, notes, area, language, submitted_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (sub_id, title, url, payload.notes, payload.area or "General", payload.language, payload.name, created_at),
        )
    return {
        "id": sub_id,
        "title": title,
        "url": url,
        "notes": payload.notes,
        "area": payload.area or "General",
        "language": payload.language,
        "submitted_by": payload.name,
    }


def _ensure_uid(request: Request, response: Response) -> tuple[str, bool]:
    """Garantiza identidad anónima: devuelve (uid, admin) y fija la cookie si faltaba."""
    cookie = request.cookies.get(SESSION_COOKIE)
    sess = parse_session(cookie)
    if sess and sess.get("uid"):
        uid = sess["uid"]
        return uid, session_admin(uid, bool(sess.get("admin")))
    uid = secrets.token_hex(16)
    set_session_cookie(response, make_session(uid, admin=False), 60 * 60 * 24 * 365)
    return uid, False


# --- Índice federado de recursos (búsqueda unificada) ---

def _norm(s: str) -> str:
    return re.sub(r"[\u0300-\u036f]", "", s or "").lower()


@app.get("/api/resources")
def list_resources(
    q: str = "",
    provider: str = "",
    format: str = "",
    subject: str = "",
    stage: str = "",
    language: str = "",
    license: str = "",
    license_known: bool | None = None,
    limit: int = 48,
    offset: int = 0,
) -> dict:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    where = ["active = 1"]
    params: list = []

    if provider:
        where.append("provider = ?")
        params.append(provider)
    if format:
        where.append("format = ?")
        params.append(format)
    if subject:
        where.append("subject = ?")
        params.append(subject)
    if stage:
        where.append("educational_stage = ?")
        params.append(stage)
    if language:
        where.append("language LIKE ?")
        params.append(f'%"{language}"%')
    if license:
        where.append("license = ?")
        params.append(license)
    if license_known is not None:
        where.append("license_known = ?")
        params.append(1 if license_known else 0)

    term = _norm(q).strip()
    if term:
        where.append(
            "(lower(title) LIKE ? OR lower(COALESCE(title_ca,'')) LIKE ? "
            "OR lower(COALESCE(description,'')) LIKE ? OR lower(COALESCE(description_ca,'')) LIKE ? "
            "OR lower(COALESCE(author,'')) LIKE ? OR lower(tags) LIKE ? OR lower(external_id) LIKE ?)"
        )
        like = f"%{term}%"
        params.extend([like, like, like, like, like, like, like])

    where_sql = " WHERE " + " AND ".join(where)

    with get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM resources{where_sql}", params
        ).fetchone()["n"]
        rows = conn.execute(
            f"SELECT * FROM resources{where_sql} ORDER BY title LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [Resource.from_row(r).to_dict() for r in rows],
    }


@app.get("/api/admin/sources")
def admin_sources(request: Request) -> dict:
    uid, admin = get_session(request)
    if not admin:
        raise HTTPException(status_code=403, detail="admin required")
    with get_conn() as conn:
        counts = {
            r["provider"]: r["n"]
            for r in conn.execute(
                "SELECT provider, COUNT(*) AS n FROM resources WHERE active = 1 GROUP BY provider"
            )
        }
        last = {}
        for r in conn.execute(
            "SELECT * FROM sync_runs WHERE id IN (SELECT MAX(id) FROM sync_runs GROUP BY provider)"
        ):
            last[r["provider"]] = {
                "status": r["status"],
                "fetched": r["fetched"],
                "created": r["created"],
                "updated": r["updated"],
                "unchanged": r["unchanged"],
                "errors": r["errors"],
                "started_at": r["started_at"],
                "finished_at": r["finished_at"],
            }
    return {
        "providers": [
            {
                "provider": p,
                "resources": counts.get(p, 0),
                "last_sync": last.get(p),
            }
            for p in sorted(counts)
        ]
    }


# --- OIDC (Authentik / EduTicTac Commons) ---

@app.get("/api/auth/login")
def auth_login() -> RedirectResponse:
    if not oidc.enabled():
        raise HTTPException(status_code=503, detail="oidc not configured")
    url, state_cookie = oidc.build_login_url()
    response = RedirectResponse(url)
    response.set_cookie(
        oidc.OIDC_STATE_COOKIE, state_cookie,
        httponly=True, secure=COOKIE_SECURE, samesite="lax", path="/api/auth", max_age=600,
    )
    return response


@app.get("/api/auth/callback")
def auth_callback(request: Request, code: str = "", state: str = "") -> RedirectResponse:
    if not oidc.enabled():
        raise HTTPException(status_code=503, detail="oidc not configured")
    if not code or not state:
        raise HTTPException(status_code=400, detail="missing code or state")
    state_cookie = request.cookies.get(oidc.OIDC_STATE_COOKIE)
    try:
        info = oidc.handle_callback(state, code, state_cookie)
    except Exception as exc:  # noqa: BLE001
        logger.warning("OIDC callback failed: %s", describe_oidc_error(exc))
        raise HTTPException(status_code=401, detail="oauth callback failed") from exc

    uid = f"oidc:{info['sub']}"
    admin = bool(info["admin"])
    response = RedirectResponse("/")
    set_session_cookie(response, make_session(uid, admin=admin), 60 * 60 * 24 * 30)
    response.delete_cookie(
        oidc.OIDC_STATE_COOKIE,
        path="/api/auth",
        secure=COOKIE_SECURE,
        samesite="lax",
    )
    return response


@app.get("/api/auth/logout")
def auth_logout() -> RedirectResponse:
    response = RedirectResponse("/")
    delete_session_cookie(response)
    return response


@app.get("/api/auth/me")
def auth_me(request: Request) -> dict:
    uid, admin = get_session(request)
    logged_in = bool(uid.startswith("oidc:"))
    sub = uid[len("oidc:"):] if logged_in else ""
    return {
        "logged_in": logged_in,
        "admin": admin,
        "sub": sub,
        "admin_sub": sub,
    }
