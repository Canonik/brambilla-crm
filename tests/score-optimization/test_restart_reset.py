"""Restart/reset regression in disposable local PostgreSQL schemas.

SCORE_DATABASE_URL must identify an authorized loopback DB. No shared reset,
production request, model call, or modification of another schema occurs.
"""
import contextlib
import importlib
import os
from pathlib import Path
import uuid

import pytest


@pytest.fixture
def account(monkeypatch):
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
    from fastapi.testclient import TestClient

    dsn = os.environ.get("SCORE_DATABASE_URL")
    if not dsn:
        pytest.skip("Set SCORE_DATABASE_URL to the authorized local PostgreSQL instance")
    assert conninfo_to_dict(dsn).get("host") in {"127.0.0.1", "localhost", "::1"}
    root = Path(os.environ.get("SCORE_SERVER_ROOT", Path(__file__).resolve().parents[2] / "server"))
    monkeypatch.syspath_prepend(str(root))
    db = importlib.import_module("app.db")
    config = importlib.import_module("app.config")
    store_module = importlib.import_module("app.store")
    brambilla = importlib.import_module("app.brambilla")
    rules = importlib.import_module("app.rules")
    lists = importlib.import_module("app.routers.lists")
    main = importlib.import_module("app.main")
    schema = "score_restart_" + uuid.uuid4().hex
    isolated_dsn = make_conninfo(dsn, options=f"-c search_path={schema}")
    admin = psycopg.connect(dsn, autocommit=True)

    @contextlib.contextmanager
    def connection():
        with psycopg.connect(isolated_dsn, row_factory=dict_row) as conn:
            assert conn.execute("SELECT current_schema() AS name").fetchone()["name"] == schema
            yield conn

    monkeypatch.setattr(db, "connection", connection)
    monkeypatch.setattr(config, "API_TOKEN", "restart-local-only")
    try:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        store_module.invalidate_caches()
        with TestClient(main.app) as client:
            client.headers["Authorization"] = "Bearer restart-local-only"
            with connection() as conn:
                brambilla.ensure_all(conn)
                store_module.invalidate_caches()
                store = store_module.Store(conn)
                rules.ensure_deal_pipeline(store)
                rules.ensure_ticket_pipeline(store)
                company = store.create("companies", {"name": "Restart customer", "partita_iva": "12345678901"})
                custom_group = {"name": "retained", "label": "Retained group"}
                conn.execute("INSERT INTO property_groups VALUES (%s,%s,%s)", ("companies", "retained", Jsonb(custom_group)))
                conn.execute("INSERT INTO association_labels VALUES (900001,'companies','contacts','Purchasing','purchasing','USER_DEFINED',NULL)")
                conn.execute("UPDATE properties SET definition=jsonb_set(definition,'{label}',%s) WHERE object_type='companies' AND name='name'", (Jsonb("Edited company label"),))
                conn.execute("UPDATE pipelines SET definition=jsonb_set(definition,'{label}',%s) WHERE object_type='deals' AND id='default'", (Jsonb("Edited sales label"),))
                created_list = lists.create_list(conn, "Clienti dormienti", "0-2")
                conn.execute("INSERT INTO list_memberships VALUES (%s,%s,now())", (int(created_list["listId"]), int(company["id"])))
                conn.execute("INSERT INTO meta VALUES ('migration',%s)", (Jsonb({"records": 1}),))
            store_module.invalidate_caches()
            yield client, connection, db, main, company["id"]
    finally:
        store_module.invalidate_caches()
        admin.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
        admin.close()


def metadata(connection):
    # Exact JSON definitions include timestamps and edits to default metadata.
    with connection() as conn:
        return {
            "properties": conn.execute("SELECT * FROM properties ORDER BY object_type,name").fetchall(),
            "groups": conn.execute("SELECT * FROM property_groups ORDER BY object_type,name").fetchall(),
            "pipelines": conn.execute("SELECT * FROM pipelines ORDER BY object_type,id").fetchall(),
            "labels": conn.execute("SELECT * FROM association_labels ORDER BY type_id").fetchall(),
        }


def test_startup_preserves_all_metadata_and_default_edits(account):
    client, connection, db, _, company_id = account
    expected = metadata(connection)
    for _ in range(2):
        db.init_schema()
        assert metadata(connection) == expected
    assert client.get(f"/crm/v3/objects/companies/{company_id}").status_code == 200
    assert client.get("/crm/v3/properties/companies/partita_iva").json()["hasUniqueValue"] is True


def test_explicit_reset_removes_custom_state_and_restores_defaults(account):
    client, connection, db, main, company_id = account
    db.init_schema()
    for _ in range(2):
        response = client.post("/__reset")
        assert response.status_code == 204 and response.content == b""
        assert main.rate.count == 0 and main.rate.daily == 0
        with connection() as conn:
            for table in ("objects", "associations", "lists", "list_memberships", "meta"):
                assert conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"] == 0
            assert conn.execute("SELECT count(*) AS n FROM properties WHERE name IN ('id_legacy','partita_iva')").fetchone()["n"] == 0
            assert not conn.execute("SELECT 1 FROM property_groups WHERE name='retained'").fetchone()
            assert not conn.execute("SELECT 1 FROM association_labels WHERE type_id=900001").fetchone()
            assert conn.execute("SELECT definition->>'label' AS label FROM properties WHERE object_type='companies' AND name='name'").fetchone()["label"] != "Edited company label"
            pipelines = conn.execute("SELECT object_type,id,definition->>'label' AS label FROM pipelines ORDER BY object_type,id").fetchall()
            assert pipelines == [
                {"object_type": "deals", "id": "default", "label": "Sales Pipeline"},
                {"object_type": "tickets", "id": "0", "label": "Support Pipeline"},
            ]
        assert client.get(f"/crm/v3/objects/companies/{company_id}").status_code == 404
        expected = metadata(connection)
        db.init_schema()
        assert metadata(connection) == expected
