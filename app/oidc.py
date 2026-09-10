"""Integración OIDC con Authentik (EduTicTac Commons).

Thin wrapper sobre `edutictac_community.oidc.OIDCClient` que conserva la
superficie usada por `main.py` (enabled / build_login_url / handle_callback /
is_admin_sub / OIDC_STATE_COOKIE). El flujo es authorization code + PKCE.
"""
from __future__ import annotations

import os

from edutictac_community.oidc import OIDCClient

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
OIDC_ADMIN_SUBS = {
    s.strip()
    for s in os.environ.get("OIDC_ADMIN_SUBS", "").split(",")
    if s.strip()
}

SESSION_SECRET = os.environ.get("RECURSOS_SECRET", "")
OIDC_STATE_COOKIE = "recursos_oidc_state"

_client = OIDCClient(
    OIDC_CLIENT_ID,
    OIDC_CLIENT_SECRET,
    OIDC_ISSUER,
    OIDC_REDIRECT_URI,
    scope=OIDC_SCOPE,
    session_secret=SESSION_SECRET,
    state_cookie_name=OIDC_STATE_COOKIE,
    user_agent="EduTicTac-Resources/0.1",
    admin_subjects=OIDC_ADMIN_SUBS,
    admin_emails=OIDC_ADMIN_EMAILS,
)


def enabled() -> bool:
    return _client.enabled()


def is_admin_sub(sub: str) -> bool:
    return sub in OIDC_ADMIN_SUBS


def build_login_url() -> tuple[str, str]:
    return _client.build_login_url()


def handle_callback(state: str, code: str, state_cookie: str | None) -> dict:
    return _client.handle_callback(state, code, state_cookie)
