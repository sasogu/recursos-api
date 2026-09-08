"""Integración OIDC con Authentik (EduTicTac Commons).

Flujo authorization code + PKCE (authlib). El usuario logueado obtiene una
identidad real (`oidc:<sub>`); los visitantes siguen usando la cookie anónima.
El correo de los docentes/admin se compara contra OIDC_ADMIN_EMAILS para marcar
el rol admin (sin que el correo viaje a ningún servicio externo).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets

import httpx
from authlib.integrations.httpx_client import OAuth2Client

OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "")
OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "")
OIDC_REDIRECT_URI = os.environ.get("OIDC_REDIRECT_URI", "")
OIDC_ADMIN_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("OIDC_ADMIN_EMAILS", "").split(",")
    if e.strip()
}

SESSION_SECRET = os.environ.get("RECURSOS_SECRET", "")
OIDC_STATE_COOKIE = "recursos_oidc_state"

_META: dict | None = None


def enabled() -> bool:
    return bool(
        OIDC_CLIENT_ID and OIDC_CLIENT_SECRET and OIDC_ISSUER and OIDC_REDIRECT_URI
    )


def _metadata() -> dict:
    global _META
    if _META is None:
        url = OIDC_ISSUER.rstrip("/") + "/.well-known/openid-configuration"
        resp = httpx.get(url, timeout=20, headers={"User-Agent": "EduTicTac-Resources/0.1"})
        resp.raise_for_status()
        _META = resp.json()
    return _META


def _client() -> OAuth2Client:
    return OAuth2Client(
        OIDC_CLIENT_ID,
        OIDC_CLIENT_SECRET,
        redirect_uri=OIDC_REDIRECT_URI,
        scope="openid profile email",
    )


def _sign(data: str) -> str:
    return hmac.new(SESSION_SECRET.encode(), data.encode(), hashlib.sha256).hexdigest()


def _encode(payload: dict) -> str:
    data = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    return f"{data}.{_sign(data)}"


def _decode(cookie: str | None) -> dict | None:
    if not cookie or not SESSION_SECRET:
        return None
    try:
        data, sig = cookie.split(".", 1)
        if not hmac.compare_digest(sig, _sign(data)):
            return None
        return json.loads(base64.urlsafe_b64decode(data.encode()).decode())
    except Exception:
        return None


def build_login_url() -> tuple[str, str]:
    """Devuelve (url_de_autorización, cookie_de_estado firmada con code_verifier)."""
    meta = _metadata()
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    client = _client()
    uri, _ = client.create_authorization_url(
        meta["authorization_endpoint"],
        state,
        code_challenge=code_challenge,
        code_challenge_method="S256",
    )
    cookie = _encode({"state": state, "code_verifier": code_verifier})
    return uri, cookie


def handle_callback(state: str, code: str, state_cookie: str | None) -> dict:
    saved = _decode(state_cookie)
    if not saved or saved.get("state") != state:
        raise ValueError("state mismatch")

    meta = _metadata()
    client = _client()
    token = client.fetch_token(
        meta["token_endpoint"],
        code=code,
        code_verifier=saved.get("code_verifier", ""),
    )
    userinfo = client.get(meta["userinfo_endpoint"]).json()
    sub = str(userinfo.get("sub", ""))
    email = (userinfo.get("email") or "").lower()
    return {
        "sub": sub,
        "email": email,
        "name": userinfo.get("name", "") or userinfo.get("preferred_username", ""),
        "admin": email in OIDC_ADMIN_EMAILS,
    }
