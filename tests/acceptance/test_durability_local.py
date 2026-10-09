"""Restart persistence, runnable only where we control the process: set DOCKER_CONTAINER to the
name of the running CRM container (built from the root Dockerfile) and the test restarts it."""
import os
import subprocess
import time
import uuid

import pytest

CONTAINER = os.environ.get("DOCKER_CONTAINER")
pytestmark = pytest.mark.skipif(not CONTAINER, reason="DOCKER_CONTAINER not set")


def test_data_survives_restart(client, base_url):
    e = f"durable.{uuid.uuid4().hex[:8]}@example.com"
    c = client.post("/crm/v3/objects/contacts", json={"properties": {"email": e, "firstname": "Durable"}})
    assert c.status_code == 201
    cid = c.json()["id"]
    subprocess.run(["docker", "restart", CONTAINER], check=True, capture_output=True)
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            if client.get("/health").status_code == 200:
                break
        except Exception:
            pass
        time.sleep(1)
    r = client.get(f"/crm/v3/objects/contacts/{cid}")
    assert r.status_code == 200
    assert r.json()["properties"]["email"] == e
