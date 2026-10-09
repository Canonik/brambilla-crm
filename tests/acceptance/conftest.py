"""Black-box acceptance tests. They talk HTTP to a running CRM, local or on Railway.

Env: BASE_URL (default http://127.0.0.1:8000), CRM_TOKEN (default dev-token),
EXPORT_ZIP (default legacy/export.zip), EXPORT_URL (optional: a public URL of the export; when
unset a local file server is started so a local CRM can download the sample export).
Tests marked `migration` reset the CRM and run the migration once per session (slow).
"""
import functools
import http.server
import os
import socket
import threading
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TOKEN = os.environ.get("CRM_TOKEN", "dev-token")
EXPORT_ZIP = Path(os.environ.get("EXPORT_ZIP", ROOT / "legacy" / "export.zip"))


def pytest_configure(config):
    config.addinivalue_line("markers", "migration: resets the CRM and migrates the sample export")
    config.addinivalue_line("markers", "assistant: calls the model key, costs money")


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture(scope="session")
def token():
    return TOKEN


@pytest.fixture(scope="session")
def client(base_url, token):
    with httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {token}"}, timeout=30) as c:
        yield c


@pytest.fixture(scope="session")
def anon(base_url):
    with httpx.Client(base_url=base_url, timeout=30) as c:
        yield c


def _free_port():
    s = socket.socket()
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="session")
def export_url():
    """URL the CRM can download the sample export from."""
    if os.environ.get("EXPORT_URL"):
        return os.environ["EXPORT_URL"]
    if not EXPORT_ZIP.exists():
        pytest.skip("no export zip available")
    port = _free_port()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(EXPORT_ZIP.parent))
    handler.log_message = lambda *a, **k: None  # type: ignore[attr-defined]
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", port), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    host = os.environ.get("EXPORT_HOST", "127.0.0.1")
    yield f"http://{host}:{port}/{EXPORT_ZIP.name}?token=abc&x=1"
    srv.shutdown()


@pytest.fixture(scope="session")
def migrated(client, export_url):
    """Reset and migrate once per session; returns elapsed seconds."""
    import time

    r = client.post("/__reset")
    assert r.status_code == 204, r.text
    t0 = time.time()
    r = client.post("/__migrate", json={"export_url": export_url}, timeout=330)
    elapsed = time.time() - t0
    assert r.status_code == 204, f"migrate -> {r.status_code}: {r.text[:500]}"
    return elapsed


def search(client, object_type, filters=None, properties=None, limit=100, after=None, sorts=None, query=None):
    body = {"limit": limit}
    if filters:
        body["filterGroups"] = [{"filters": filters}]
    if properties:
        body["properties"] = properties
    if after is not None:
        body["after"] = str(after)
    if sorts:
        body["sorts"] = sorts
    if query:
        body["query"] = query
    r = client.post(f"/crm/v3/objects/{object_type}/search", json=body)
    assert r.status_code == 200, f"search {object_type}: {r.status_code} {r.text[:300]}"
    return r.json()


def by_legacy(client, object_type, id_legacy, properties=None):
    res = search(client, object_type, [{"propertyName": "id_legacy", "operator": "EQ", "value": str(id_legacy)}], properties, limit=5)
    assert res["total"] <= 1, f"{object_type} id_legacy={id_legacy} not unique: {res}"
    return res["results"][0] if res["results"] else None


def assoc_ids(client, object_type, object_id, to_type):
    r = client.get(f"/crm/v4/objects/{object_type}/{object_id}/associations/{to_type}", params={"limit": 500})
    assert r.status_code == 200, r.text[:300]
    return {str(x["toObjectId"]) for x in r.json()["results"]}
