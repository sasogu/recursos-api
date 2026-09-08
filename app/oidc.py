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
from authlib.jose import JsonWebKey, jwt

OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "")
OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "")
OIDC_REDIRECT_URI = os.environ.get("OIDC_REDIRECT_URI", "")
OIDC_SCOPE = os.environ.get("OIDC_SCOPE", "openid")
OIDC_ADMIN_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("OIDC_ADMIN_EMAILS", "").split(",")
    if e.strip()
}

SESSION_SECRET = os.environ.get("RECURSOS_SECRET", "")
OIDC_STATE_COOKIE = "recursos_oidc_state"

_META: dict | None = None
_JWKS = None


def enabled() -> bool:
    return bool(
        SESSION_SECRET and OIDC_CLIENT_ID and OIDC_CLIENT_SECRET and OIDC_ISSUER and OIDC_REDIRECT_URI
    )


def _metadata() -> dict:
    global _META
    if _META is None:
        url = OIDC_ISSUER.rstrip("/") + "/.well-known/openid-configuration"
        resp = httpx.get(url, timeout=20, headers={"User-Agent": "EduTicTac-Resources/0.1"})
        resp.raise_for_status()
        _META = resp.json()
    return _META


def _jwks(meta: dict):
    global _JWKS
    if _JWKS is None:
        resp = httpx.get(meta["jwks_uri"], timeout=20, headers={"User-Agent": "EduTicTac-Resources/0.1"})
        resp.raise_for_status()
        _JWKS = JsonWebKey.import_key_set(resp.json())
    return _JWKS


def _client() -> OAuth2Client:
    return OAuth2Client(
        OIDC_CLIENT_ID,
        OIDC_CLIENT_SECRET,
        redirect_uri=OIDC_REDIRECT_URI,
        scope=OIDC_SCOPE,
        token_endpoint_auth_method="client_secret_post",
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


def _userinfo_from_id_token(token: dict, meta: dict) -> dict:
    id_token = token.get("id_token") if isinstance(token, dict) else None
    if not id_token:
        return {}
    claims = jwt.decode(
        id_token,
        _jwks(meta),
        claims_options={
            "iss": {"essential": True, "value": meta["issuer"]},
            "aud": {"essential": True, "value": OIDC_CLIENT_ID},
            "sub": {"essential": True},
            "exp": {"essential": True},
        },
    )
    claims.validate(leeway=60)
    return dict(claims)


def handle_callback(state: str, code: str, state_cookie: str | None) -> dict:
    saved = _decode(state_cookie)
    if not saved or saved.get("state") != state:
        raise ValueError("state mismatch")

    meta = _metadata()
    client = _client()
    token = client.fetch_token(
        meta["token_endpoint"],
        grant_type="authorization_code",
        code=code,
        redirect_uri=OIDC_REDIRECT_URI,
        code_verifier=saved.get("code_verifier", ""),
    )
    userinfo = _userinfo_from_id_token(token, meta)
    if "sub" not in userinfo:
        resp = client.get(meta["userinfo_endpoint"])
        resp.raise_for_status()
        try:
            userinfo = resp.json()
        except ValueError as exc:
            raise ValueError("userinfo returned non-json response") from exc
        if not isinstance(userinfo, dict):
            raise ValueError("userinfo returned invalid response")
        if "sub" not in userinfo and isinstance(token, dict) and isinstance(token.get("userinfo"), dict):
            userinfo = token["userinfo"]
    sub = str(userinfo.get("sub", ""))
    if not sub:
        raise ValueError("missing subject")
    email = (userinfo.get("email") or "").lower()
    return {
        "sub": sub,
        "email": email,
        "name": userinfo.get("name", "") or userinfo.get("preferred_username", ""),
        "admin": email in OIDC_ADMIN_EMAILS,
    }
