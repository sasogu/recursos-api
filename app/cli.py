"""CLI del índice federado.

Uso:
  python -m app.cli sync jclic|h5p|scorm|eduhoot|all
  python -m app.cli sync scorm --url https://.../paquete.zip
  python -m app.cli stats
  python -m app.cli sources
"""
from __future__ import annotations

import argparse

from .db import get_conn, init_index_schema
from .models import Resource
from .providers import get_provider, get_providers
from .providers.scorm import SCORMProvider
from .sync import run_sync


def cmd_sync(args) -> int:
    init_index_schema()
    if args.provider == "all":
        names = list(get_providers())
    else:
        names = [args.provider]

    for name in names:
        if name == "scorm" and args.url:
            provider = SCORMProvider(sources_path=args.sources)
            resource = provider.ingest_from_url(args.url)
            _save_single(resource)
            print(f"SCORM ingerido: {resource.title} ({resource.external_id})")
            continue

        provider = get_provider(name)
        print(f"\nSincronizando '{provider.name}' ...")
        run = run_sync(provider)
        print(
            f"{provider.name} synchronization complete\n"
            f"Fetched: {run.fetched}\n"
            f"New: {run.created}\n"
            f"Updated: {run.updated}\n"
            f"Unchanged: {run.unchanged}\n"
            f"Errors: {run.errors}\n"
            f"Status: {run.status}"
        )
    return 0


def _save_single(resource: Resource) -> None:
    init_index_schema()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO resources (provider, external_id, title, description, author, "
            "license, license_known, language, resource_type, format, subject, "
            "educational_stage, educational_level, tags, source_url, play_url, "
            "download_url, reuse_url, thumbnail_url, metadata_json, created_at_source, "
            "updated_at_source, indexed_at, last_synced_at, active) "
            "VALUES (:provider, :external_id, :title, :description, :author, :license, "
            ":license_known, :language, :resource_type, :format, :subject, "
            ":educational_stage, :educational_level, :tags, :source_url, :play_url, "
            ":download_url, :reuse_url, :thumbnail_url, :metadata_json, :created_at_source, "
            ":updated_at_source, :indexed_at, :last_synced_at, :active) "
            "ON CONFLICT(provider, external_id) DO UPDATE SET "
            "title=excluded.title, description=excluded.description, author=excluded.author, "
            "license=excluded.license, license_known=excluded.license_known, "
            "language=excluded.language, resource_type=excluded.resource_type, format=excluded.format, "
            "subject=excluded.subject, educational_stage=excluded.educational_stage, "
            "educational_level=excluded.educational_level, tags=excluded.tags, "
            "source_url=excluded.source_url, play_url=excluded.play_url, "
            "download_url=excluded.download_url, reuse_url=excluded.reuse_url, "
            "thumbnail_url=excluded.thumbnail_url, metadata_json=excluded.metadata_json, "
            "created_at_source=excluded.created_at_source, updated_at_source=excluded.updated_at_source, "
            "last_synced_at=excluded.last_synced_at, active=1",
            resource.to_row(),
        )


def cmd_stats(_args) -> int:
    init_index_schema()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT provider, COUNT(*) AS total, "
            "SUM(CASE WHEN active THEN 1 ELSE 0 END) AS active "
            "FROM resources GROUP BY provider ORDER BY provider"
        ).fetchall()
    if not rows:
        print("No hay recursos indexados todavía.")
        return 0
    print(f"{'Provider':<12} {'Activos':>8} {'Total':>8}")
    for r in rows:
        print(f"{r['provider']:<12} {r['active']:>8} {r['total']:>8}")
    return 0


def cmd_sources(_args) -> int:
    init_index_schema()
    with get_conn() as conn:
        last = {
            r["provider"]: dict(r)
            for r in conn.execute(
                "SELECT * FROM sync_runs WHERE id IN "
                "(SELECT MAX(id) FROM sync_runs GROUP BY provider)"
            )
        }
        counts = {
            r["provider"]: r["n"]
            for r in conn.execute(
                "SELECT provider, COUNT(*) AS n FROM resources WHERE active = 1 GROUP BY provider"
            )
        }
    providers = get_providers()
    print("Fuentes de recursos")
    print("=" * 60)
    for name in sorted(providers):
        run = last.get(name)
        count = counts.get(name, 0)
        status = run["status"] if run else "—"
        last_sync = run["finished_at"] if run else "nunca"
        print(f"{name}:")
        print(f"  Estado: {status}")
        print(f"  Recursos: {count}")
        print(f"  Última sincronización: {last_sync}")
        if run:
            print(
                f"  Último sync: {run['fetched']} fetched, {run['created']} nuevos, "
                f"{run['updated']} actualizados, {run['errors']} errores"
            )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="recursos", description="Índice federado de REA")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sync = sub.add_parser("sync", help="sincroniza un proveedor")
    p_sync.add_argument("provider", choices=["jclic", "h5p", "scorm", "eduhoot", "all"])
    p_sync.add_argument("--url", help="URL de un paquete SCORM a ingerir")
    p_sync.add_argument("--sources", help="ruta a scorm-sources.json (provider scorm)")
    p_sync.set_defaults(func=cmd_sync)

    p_stats = sub.add_parser("stats", help="recursos indexados por proveedor")
    p_stats.set_defaults(func=cmd_stats)

    p_sources = sub.add_parser("sources", help="estado de las fuentes")
    p_sources.set_defaults(func=cmd_sources)

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
