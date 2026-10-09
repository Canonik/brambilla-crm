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


def test_list_reads_report_row_counts_and_store_totals():
    observer = EvidenceTrace(True)
    call = observer.begin("search_companies", {"name": "Mazza"})
    observer.returned(call, {"total": 3, "results": [{"id": "1", "name": "SECRET"}, {"id": "2"}]})
    event = observer.snapshot()["events"][-1]
    assert event["count"] == 2 and event["total"] == 3
    none = EvidenceTrace(True)
    call = none.begin("search_deals", {})
    none.returned(call, {"total": 0, "results": []})
    event = none.snapshot()["events"][-1]
    assert event["status"] == "completed" and event["count"] == 0 and event["records"] == []


def test_relations_are_only_between_accepted_records_and_mirror_the_tool_result():
    observer = EvidenceTrace(True)
    call = observer.begin("company_overview", {"company_id": "18"})
    observer.returned(call, {
        "company": {"id": "18", "name": "SECRET"},
        "contacts": [{"id": "77", "email": "SECRET"}],
        "deals": [{"id": "42"}, {"id": "0"}],
        "tickets": [],
        "last_activities": [{"type": "notes", "id": "900"}, {"type": "unknown", "id": "901"}],
    })
    event = observer.snapshot()["events"][-1]
    assert event["records"] == [{"type": "companies", "id": "18"}, {"type": "contacts", "id": "77"}, {"type": "deals", "id": "42"}, {"type": "notes", "id": "900"}]
    assert event["relations"] == [
        {"from": {"type": "companies", "id": "18"}, "to": {"type": "contacts", "id": "77"}},
        {"from": {"type": "companies", "id": "18"}, "to": {"type": "deals", "id": "42"}},
        {"from": {"type": "companies", "id": "18"}, "to": {"type": "notes", "id": "900"}},
    ]
    assert "SECRET" not in json.dumps(event)

    writes = EvidenceTrace(True)
    call = writes.begin("associate", {"from_type": "deals", "from_id": "42", "to_type": "contacts", "to_id": "77"})
    writes.returned(call, {"ok": True})
    writes.transaction_finished(call, "committed")
    event = writes.snapshot()["events"][-1]
    assert event["status"] == "committed"
    assert event["relations"] == [{"from": {"type": "deals", "id": "42"}, "to": {"type": "contacts", "id": "77"}}]

    rejected = EvidenceTrace(True)
    call = rejected.begin("associate", {"from_type": "deals", "from_id": "42", "to_type": "contacts", "to_id": "77"})
    rejected.returned(call, {"error": "SECRET", "status": 404})
    event = rejected.snapshot()["events"][-1]
    assert event["status"] == "rolled_back" and "relations" not in event and event["records"] == []


def test_search_rows_link_to_the_company_the_store_resolved():
    observer = EvidenceTrace(True)
    call = observer.begin("search_deals", {"name": "Fornitura"})
    observer.returned(call, {"total": 1, "results": [{"id": "42", "company_id": "18", "company_name": "SECRET"}]})
    event = observer.snapshot()["events"][-1]
    assert event["records"] == [{"type": "deals", "id": "42"}, {"type": "companies", "id": "18"}]
    assert event["relations"] == [{"from": {"type": "deals", "id": "42"}, "to": {"type": "companies", "id": "18"}}]
    assert "SECRET" not in json.dumps(event)


def test_failure_category_comes_from_the_numeric_status_only():
    observer = EvidenceTrace(True)
    conflict = observer.begin("create_record", {"object_type": "companies", "properties": {"partita_iva": "SECRET"}})
    observer.returned(conflict, {"error": "partita IVA SECRET già presente", "status": 409})
    missing = observer.begin("get_record", {"object_type": "deals", "id": "999"})
    observer.returned(missing, {"error": "SECRET", "status": 404})
    rule = observer.begin("update_record", {"object_type": "deals", "id": "42", "properties": {}})
    observer.returned(rule, {"error": "SECRET regola aziendale"})
    raised = observer.begin("search_companies", {"name": "x"})
    observer.failed(raised, reason="not a kind")
    events = {event["call"]: event for event in observer.snapshot()["events"] if "failure" in event}
    assert events[1]["failure"] == "conflict" and events[1]["status"] == "rolled_back"
    assert events[2]["failure"] == "not_found" and events[2]["status"] == "failed"
    assert events[3]["failure"] == "rejected"
    assert events[4]["failure"] == "error"
    assert "SECRET" not in json.dumps(list(events.values()))


def test_relations_and_counts_stay_inside_the_byte_budget():
    observer = EvidenceTrace(True)
    for index in range(1, 40):
        call = observer.begin("company_overview", {"company_id": str(index)})
        observer.returned(call, {"company": {"id": str(index)}, "deals": [{"id": str(1000 * index + offset)} for offset in range(1, 60)]})
    value = observer.snapshot()
    assert value["incomplete"] is True
    assert len(json.dumps(value, separators=(",", ":")).encode()) <= 32_768
    assert all(len(event.get("relations", [])) <= 40 for event in value["events"])
