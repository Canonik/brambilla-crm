import json
from concurrent.futures import ThreadPoolExecutor

from app.assistant.evidence import EvidenceTrace


def test_observer_is_default_off_and_unknown_tools_fail_closed():
    assert EvidenceTrace().snapshot() is None
    observer = EvidenceTrace(True)
    assert observer.begin("model_invented_tool", {"secret": "SECRET"}) is None
    value = observer.snapshot()
    assert value == {"version": 1, "events": [], "incomplete": True}
    assert "SECRET" not in json.dumps(value)


def test_observer_bounds_records_and_never_copies_raw_payloads():
    observer = EvidenceTrace(True)
    call = observer.begin("search_deals", {"query": "SECRET", "credential": "SECRET"})
    observer.returned(call, {"results": [{"id": str(index), "name": "SECRET"} for index in range(1, 40)], "raw": "SECRET"})
    value = observer.snapshot()
    assert value["incomplete"] is True
    assert len(value["events"][-1]["records"]) == 20
    assert len(json.dumps(value, separators=(",", ":")).encode()) <= 32_768
    assert "SECRET" not in json.dumps(value)


def test_write_return_is_not_commit_and_outcome_is_explicit():
    observer = EvidenceTrace(True)
    call = observer.begin("update_record", {"object_type": "deals", "id": "42", "properties": {"description": "SECRET"}})
    observer.returned(call, {"ok": True, "object_type": "deals", "id": "42", "properties": {"description": "SECRET"}})
    assert observer.snapshot()["events"][-1]["status"] == "awaiting_commit"
    observer.transaction_finished(call, "committed")
    value = observer.snapshot()
    assert [event["status"] for event in value["events"]] == ["attempted", "awaiting_commit", "committed"]
    assert value["events"][-1]["records"] == [{"type": "deals", "id": "42"}]
    assert "SECRET" not in json.dumps(value)


def test_four_request_local_observers_do_not_mix_records():
    def observe(index: int):
        observer = EvidenceTrace(True)
        call = observer.begin("search_companies", {"query": f"customer-{index}"})
        observer.returned(call, {"results": [{"id": str(index), "name": f"customer-{index}"}]})
        return observer.snapshot()

    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(pool.map(observe, range(1, 5)))
    assert [value["events"][-1]["records"][0]["id"] for value in values] == ["1", "2", "3", "4"]
