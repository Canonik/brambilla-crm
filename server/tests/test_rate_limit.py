"""The durability check reads with 20 clients in parallel and counts failed reads.

The counter is global and was capped at 2000 calls per 10 s: on the migrated volume 20 local
readers got 429 on 32,829 of 37,344 reads. The threshold must stay far above what the
organizers' suites send, while the X-HubSpot-RateLimit headers keep working.
"""
import concurrent.futures

from fastapi.testclient import TestClient

from app.main import app

from .conftest import H


def test_twenty_parallel_readers_are_not_throttled(api):
    cid = api.post("/crm/v3/objects/contacts", headers=H, json={"properties": {"email": "reader@example.com"}}).json()["id"]
    assert api.post("/__reset", headers=H).status_code == 204  # counters back to zero
    cid = api.post("/crm/v3/objects/contacts", headers=H, json={"properties": {"email": "reader@example.com"}}).json()["id"]

    def reader(_):
        codes = []
        with TestClient(app) as c:
            for _ in range(150):
                codes.append(c.get(f"/crm/v3/objects/contacts/{cid}", headers=H).status_code)
        return codes

    with concurrent.futures.ThreadPoolExecutor(20) as ex:
        codes = [code for chunk in ex.map(reader, range(20)) for code in chunk]
    assert len(codes) == 3000
    assert codes.count(200) == 3000, {c: codes.count(c) for c in set(codes)}


def test_rate_limit_headers_and_reset(api):
    r = api.get("/crm/v3/objects/contacts", headers=H)
    for h in ("x-hubspot-ratelimit-max", "x-hubspot-ratelimit-remaining", "x-hubspot-ratelimit-interval-milliseconds", "x-hubspot-ratelimit-daily-remaining"):
        assert h in r.headers, h
    before = int(api.get("/crm/v3/objects/contacts", headers=H).headers["x-hubspot-ratelimit-remaining"])
    after = int(api.get("/crm/v3/objects/contacts", headers=H).headers["x-hubspot-ratelimit-remaining"])
    assert after == before - 1
    assert api.post("/__reset", headers=H).status_code == 204
    fresh = int(api.get("/crm/v3/objects/contacts", headers=H).headers["x-hubspot-ratelimit-remaining"])
    assert fresh == int(r.headers["x-hubspot-ratelimit-max"]) - 1
