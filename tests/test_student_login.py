import importlib
from http.cookies import SimpleCookie
from types import SimpleNamespace

from fastapi import Response


class FakeIdResponse:
    status_code = 200

    def json(self):
        return {
            "identity": {
                "id": "ident-1",
                "public_code": "K7P",
            }
        }


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
