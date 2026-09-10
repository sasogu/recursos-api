import importlib
import sys
from http.cookies import SimpleCookie
from pathlib import Path
from types import SimpleNamespace

from fastapi import Response
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class FakeIdResponse:
    status_code = 200

    def json(self):
        return {
            "identity": {
                "id": "ident-1",
                "public_code": "K7P",
            }
        }


class FakeBatchResponse:
    status_code = 201

    def json(self):
        return {
            "group": {"id": "batch-1"},
            "identities": [
                {"public_code": "K7P", "pin": "1234"},
                {"public_code": "M8Q", "pin": "5678"},
            ],
        }


class FakeSummaryResponse:
    status_code = 200

    def json(self):
        return {
            "total": 2,
            "active": 2,
            "inactive": 0,
            "groups": [{"id": "batch-1", "total": 2, "active": 2, "created_at": "2026-09-10T13:00:00+00:00"}],
        }


class FakeIdentitiesResponse:
    status_code = 200

    def json(self):
        return {
            "identities": [
                {"id": "ident-1", "public_code": "K7P", "active": True},
                {"id": "ident-2", "public_code": "M8Q", "active": True},
            ]
        }


class FakeRegeneratePinResponse:
    status_code = 200

    def json(self):
        return {"id": "ident-1", "pin": "4321"}


def load_main(tmp_path, monkeypatch):
    monkeypatch.setenv("RECURSOS_DB", str(tmp_path / "recursos.db"))
    monkeypatch.setenv("RECURSOS_SECRET", "test-secret")
    monkeypatch.setenv("RECURSOS_COOKIE_SECURE", "0")
    monkeypatch.setenv("EDUTICTAC_ID_API_URL", "https://id-api.example.test")
    import app.config
    import app.db

    importlib.reload(app.config)
    importlib.reload(app.db)
    import main

    importlib.reload(main)
    return main


def request():
    return SimpleNamespace(cookies={}, client=SimpleNamespace(host="127.0.0.1"))


def test_student_login_creates_pseudonymous_session(tmp_path, monkeypatch):
    main = load_main(tmp_path, monkeypatch)
    calls = []

    def fake_post(url, json, timeout):
        calls.append({"url": url, "json": json, "timeout": timeout})
        return FakeIdResponse()

    monkeypatch.setattr(main.httpx, "post", fake_post)
    response = Response()
    result = main.student_login(
        main.StudentLoginIn(public_code="k7p", pin="1234"),
        request(),
        response,
    )

    assert result == {"ok": True, "student_code": "K7P"}
    assert calls == [
        {
            "url": "https://id-api.example.test/api/auth/student",
            "json": {"public_code": "k7p", "pin": "1234"},
            "timeout": 10,
        }
    ]
    cookie = next(value.decode() for key, value in response.raw_headers if key.lower() == b"set-cookie")
    jar = SimpleCookie()
    jar.load(cookie)
    session_value = jar[main.SESSION_COOKIE].value
    parsed = main.parse_session(session_value)
    assert parsed["uid"] == "student:K7P:ident-1"
    assert parsed["admin"] is False


def test_teacher_can_generate_student_batch(tmp_path, monkeypatch):
    main = load_main(tmp_path, monkeypatch)
    monkeypatch.setattr(main, "EDUTICTAC_ID_TEACHER_TOKEN", "teacher-secret")
    calls = []

    def fake_post(url, json, headers=None, timeout=None):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return FakeBatchResponse()

    monkeypatch.setattr(main.httpx, "post", fake_post)
    teacher_cookie = main.make_session("oidc:teacher-sub", admin=False)
    result = main.create_student_batch(
        main.StudentBatchIn(count=2, pin_length=4),
        SimpleNamespace(cookies={main.SESSION_COOKIE: teacher_cookie}, client=SimpleNamespace(host="127.0.0.1")),
    )

    assert result == {
        "batch_id": "batch-1",
        "credentials": [{"code": "K7P", "pin": "1234"}, {"code": "M8Q", "pin": "5678"}],
    }
    assert calls == [
        {
            "url": "https://id-api.example.test/api/identities/batch",
            "json": {"count": 2, "pin_length": 4, "tenant_id": "recursos"},
            "headers": {"Authorization": "Bearer teacher-secret"},
            "timeout": 15,
        }
    ]


def test_teacher_can_read_student_summary(tmp_path, monkeypatch):
    main = load_main(tmp_path, monkeypatch)
    monkeypatch.setattr(main, "EDUTICTAC_ID_TEACHER_TOKEN", "teacher-secret")
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append({"url": url, "headers": headers, "timeout": timeout})
        return FakeSummaryResponse()

    monkeypatch.setattr(main.httpx, "get", fake_get)
    teacher_cookie = main.make_session("oidc:teacher-sub", admin=False)
    result = main.student_summary(
        SimpleNamespace(cookies={main.SESSION_COOKIE: teacher_cookie}, client=SimpleNamespace(host="127.0.0.1")),
    )

    assert result["total"] == 2
    assert result["groups"][0]["id"] == "batch-1"
    assert calls == [
        {
            "url": "https://id-api.example.test/api/teacher/summary",
            "headers": {"Authorization": "Bearer teacher-secret"},
            "timeout": 10,
        }
    ]


def test_teacher_can_list_student_identities(tmp_path, monkeypatch):
    main = load_main(tmp_path, monkeypatch)
    monkeypatch.setattr(main, "EDUTICTAC_ID_TEACHER_TOKEN", "teacher-secret")
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append({"url": url, "headers": headers, "timeout": timeout})
        return FakeIdentitiesResponse()

    monkeypatch.setattr(main.httpx, "get", fake_get)
    teacher_cookie = main.make_session("oidc:teacher-sub", admin=False)
    result = main.student_identities(
        SimpleNamespace(cookies={main.SESSION_COOKIE: teacher_cookie}, client=SimpleNamespace(host="127.0.0.1")),
    )

    assert [item["public_code"] for item in result["identities"]] == ["K7P", "M8Q"]
    assert calls == [
        {
            "url": "https://id-api.example.test/api/teacher/identities",
            "headers": {"Authorization": "Bearer teacher-secret"},
            "timeout": 10,
        }
    ]


def test_teacher_can_regenerate_student_pin(tmp_path, monkeypatch):
    main = load_main(tmp_path, monkeypatch)
    monkeypatch.setattr(main, "EDUTICTAC_ID_TEACHER_TOKEN", "teacher-secret")
    calls = []

    def fake_post(url, json=None, params=None, headers=None, timeout=None):
        calls.append({"url": url, "json": json, "params": params, "headers": headers, "timeout": timeout})
        return FakeRegeneratePinResponse()

    monkeypatch.setattr(main.httpx, "post", fake_post)
    teacher_cookie = main.make_session("oidc:teacher-sub", admin=False)
    result = main.regenerate_student_pin(
        "ident-1",
        main.PinRegenerateIn(pin_length=4),
        SimpleNamespace(cookies={main.SESSION_COOKIE: teacher_cookie}, client=SimpleNamespace(host="127.0.0.1")),
    )

    assert result == {"id": "ident-1", "pin": "4321"}
    assert calls == [
        {
            "url": "https://id-api.example.test/api/identities/ident-1/regenerate-pin",
            "json": None,
            "params": {"pin_length": 4},
            "headers": {"Authorization": "Bearer teacher-secret"},
            "timeout": 10,
        }
    ]


def test_cors_allows_edutictac_portal(tmp_path, monkeypatch):
    main = load_main(tmp_path, monkeypatch)
    cors = next(item for item in main.app.user_middleware if item.cls is CORSMiddleware)

    assert cors.kwargs["allow_origins"] == ["https://edutictac.es"]
    assert cors.kwargs["allow_credentials"] is True
    assert "POST" in cors.kwargs["allow_methods"]


def test_auth_next_url_allows_portal_and_rejects_external(tmp_path, monkeypatch):
    main = load_main(tmp_path, monkeypatch)

    assert main.auth_next_url("https://edutictac.es/tauler-professorat.html") == (
        "https://edutictac.es/tauler-professorat.html"
    )
    assert main.auth_next_url("https://evil.example/tauler-professorat.html") == "/"
    assert main.auth_next_url("http://edutictac.es/tauler-professorat.html") == "/"


def test_auth_callback_redirects_to_saved_next(tmp_path, monkeypatch):
    main = load_main(tmp_path, monkeypatch)

    monkeypatch.setattr(main.oidc, "enabled", lambda: True)
    monkeypatch.setattr(
        main.oidc,
        "handle_callback",
        lambda state, code, state_cookie: {"sub": "teacher-sub", "admin": False},
    )
    req = SimpleNamespace(
        cookies={
            main.oidc.OIDC_STATE_COOKIE: "state-cookie",
            main.AUTH_NEXT_COOKIE: "https://edutictac.es/tauler-professorat.html",
        },
        client=SimpleNamespace(host="127.0.0.1"),
    )

    response = main.auth_callback(req, code="code", state="state")

    assert response.headers["location"] == "https://edutictac.es/tauler-professorat.html"
