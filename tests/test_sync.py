"""Tests de sincronización: dedup por (provider, external_id), updated/unchanged, inactivos."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import get_conn, init_index_schema  # noqa: E402
from app.models import Resource  # noqa: E402
from app.providers.base import ResourceProvider  # noqa: E402
from app.sync import run_sync  # noqa: E402


class DummyProvider(ResourceProvider):
    name = "dummy"
    format = "dummy"

    def __init__(self, items):
        self.items = items

    def discover(self):
        yield from self.items

    def normalize(self, raw):
        return raw


def _res(ext_id, title):
    return Resource(provider="dummy", external_id=ext_id, title=title, format="dummy")


def test_sync_creates_then_updates(monkeypatch, tmp_path):
    db = tmp_path / "t.db"
    monkeypatch.setattr("app.db.config.DB_PATH", str(db))
    init_index_schema()

    run1 = run_sync(DummyProvider([_res("1", "A"), _res("2", "B")]))
    assert run1.created == 2
    assert run1.updated == 0
    assert run1.unchanged == 0
    assert run1.status == "ok"

    # Segundo sync: 1 sin cambios, 1 modificado, 1 nuevo.
    run2 = run_sync(DummyProvider([_res("1", "A"), _res("2", "B cambiado"), _res("3", "C")]))
    assert run2.created == 1
    assert run2.updated == 1
    assert run2.unchanged == 1


def test_sync_marks_missing_inactive(monkeypatch, tmp_path):
    db = tmp_path / "t.db"
    monkeypatch.setattr("app.db.config.DB_PATH", str(db))
    init_index_schema()

    run_sync(DummyProvider([_res("1", "A"), _res("2", "B")]))

    # El recurso "2" desaparece de la fuente.
    run_sync(DummyProvider([_res("1", "A")]))

    with get_conn() as conn:
        active = {
            r["external_id"]: r["active"]
            for r in conn.execute("SELECT external_id, active FROM resources")
        }
    assert active["1"] == 1
    assert active["2"] == 0


def test_sync_reactivates_reappearing_unchanged(monkeypatch, tmp_path):
    db = tmp_path / "t.db"
    monkeypatch.setattr("app.db.config.DB_PATH", str(db))
    init_index_schema()

    run_sync(DummyProvider([_res("1", "A"), _res("2", "B")]))
    # "2" desaparece y se marca inactivo.
    run_sync(DummyProvider([_res("1", "A")]))
    with get_conn() as conn:
        assert conn.execute(
            "SELECT active FROM resources WHERE external_id = '2'"
        ).fetchone()["active"] == 0

    # "2" reaparece SIN cambios de contenido: debe reactivarse (active=1).
    run_sync(DummyProvider([_res("1", "A"), _res("2", "B")]))
    with get_conn() as conn:
        assert conn.execute(
            "SELECT active FROM resources WHERE external_id = '2'"
        ).fetchone()["active"] == 1


def test_sync_isolated_error_does_not_stop(monkeypatch, tmp_path):
    db = tmp_path / "t.db"
    monkeypatch.setattr("app.db.config.DB_PATH", str(db))
    init_index_schema()

    class BadItemProvider(DummyProvider):
        def discover(self):
            yield _res("ok", "bien")
            yield None  # recurso nulo que fallará al guardarse

    run = run_sync(BadItemProvider([]))
    # El recurso roto se registra como error individual; el sync no se detiene.
    assert run.created == 1
    assert run.errors == 1
    assert run.status == "partial"


def test_sync_source_down_marks_error(monkeypatch, tmp_path):
    db = tmp_path / "t.db"
    monkeypatch.setattr("app.db.config.DB_PATH", str(db))
    init_index_schema()

    class DownProvider(DummyProvider):
        def discover(self):
            raise RuntimeError("fuente inaccesible")
            yield  # pragma: no cover

    run = run_sync(DownProvider([]))
    assert run.status == "error"
    assert run.errors == 1
    assert run.fetched == 0
