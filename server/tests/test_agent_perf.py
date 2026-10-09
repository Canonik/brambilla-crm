"""Agent-loop performance safeguards; all model and tool calls are fakes."""
import datetime as dt
import json
import threading
import time

import httpx

from app.assistant import agent
from app.assistant.evidence import EvidenceTrace
from app.assistant.tools import ToolContext


def _call(name, call_id):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": "{}"}}


def _run(monkeypatch, model, tool):
    monkeypatch.setattr(agent, "MODEL_CLIENT", model)
    monkeypatch.setattr(agent, "run_tool", tool)
    messages = [{"role": "user", "content": "test"}]
    context = ToolContext(dt.datetime(2026, 10, 9, tzinfo=dt.timezone.utc), None)
    reply = agent._run_rounds(messages, context, EvidenceTrace(False), time.monotonic(), lambda value: value)
    return reply, messages, context


def test_parallel_reads_run_concurrently_and_keep_message_order(monkeypatch):
    barrier = threading.Barrier(2)
    model_calls = 0

    def model(messages, tools, **kwargs):
        nonlocal model_calls
        model_calls += 1
        if model_calls == 1:
            return {"tool_calls": [_call("search_companies", "slow-first"), _call("get_record", "fast-second")]}
        return {"content": "fatto"}

    def tool(ctx, name, args, observer=None):
        barrier.wait(timeout=1)
        if name == "search_companies":
            time.sleep(0.04)
        return {"name": name}

    reply, messages, _ = _run(monkeypatch, model, tool)

    assert reply == "fatto"
    tool_messages = [message for message in messages if message["role"] == "tool"]
    assert [message["tool_call_id"] for message in tool_messages] == ["slow-first", "fast-second"]
    assert [json.loads(message["content"])["name"] for message in tool_messages] == ["search_companies", "get_record"]


def test_batch_containing_write_runs_entirely_sequentially(monkeypatch):
    active = 0
    max_active = 0
    order = []
    lock = threading.Lock()
    model_calls = 0

    def model(messages, tools, **kwargs):
        nonlocal model_calls
        model_calls += 1
        if model_calls == 1:
            return {"tool_calls": [_call("search_companies", "read"), _call("update_record", "write"), _call("get_record", "read-after")]}
        return {"content": "fatto"}

    def tool(ctx, name, args, observer=None):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
            order.append(name)
        time.sleep(0.02)
        if name == "update_record":
            ctx.writes.append("update deals 1")
        with lock:
            active -= 1
        return {"name": name}

    reply, _, context = _run(monkeypatch, model, tool)

    assert reply == "fatto"
    assert order == ["search_companies", "update_record", "get_record"]
    assert max_active == 1
    assert context.writes == ["update deals 1"]


def test_slow_model_call_is_shrunk_to_hard_turn_budget(monkeypatch):
    observed_timeouts = []

    def slow_model(messages, tools, *, timeout):
        observed_timeouts.append(timeout)
        time.sleep(timeout)
        raise httpx.ReadTimeout("slow fake model")

    monkeypatch.setattr(agent, "MODEL_CLIENT", slow_model)
    monkeypatch.setattr(agent, "HARD_TURN_LIMIT_S", 0.18)
    monkeypatch.setattr(agent, "TURN_BUDGET_S", 0.15)
    monkeypatch.setattr(agent, "FALLBACK_RESERVE_S", 0.03)
    started = time.monotonic()
    context = ToolContext(dt.datetime(2026, 10, 9, tzinfo=dt.timezone.utc), None)
    reply = agent._run_rounds([{"role": "user", "content": "test"}], context, EvidenceTrace(False), started, lambda value: value)
    elapsed = time.monotonic() - started

    assert "Non ho modificato" in reply
    assert len(observed_timeouts) == 1
    assert observed_timeouts[0] <= 0.151
    assert elapsed < 0.18


def test_large_read_result_keeps_total_first_rows_and_omission_count():
    result = {"total": 80, "results": [{"id": str(i), "description": "x" * 800} for i in range(80)]}

    compacted = json.loads(agent._tool_result_text(result))

    assert compacted["total"] == 80
    assert compacted["results"][0]["id"] == "0"
    assert compacted["omitted_rows"] == 70
    assert compacted["result_compacted"] is True
    assert len(json.dumps(compacted, ensure_ascii=False)) <= agent.MAX_TOOL_RESULT_CHARS


def test_write_results_are_never_compacted():
    result = {"ok": True, "results": [{"id": str(i), "description": "x" * 800} for i in range(80)]}

    text = agent._tool_result_text(result, compact=False)

    assert len(text) > agent.MAX_TOOL_RESULT_CHARS
    assert json.loads(text) == result


def test_503_is_retried_once_then_succeeds(monkeypatch):
    calls = 0
    sleeps = []

    def model(messages, tools, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise agent.ModelHTTPError(503, "temporarily unavailable")
        return {"content": "ok"}

    monkeypatch.setattr(agent, "MODEL_CLIENT", model)
    monkeypatch.setattr(agent.time, "sleep", sleeps.append)
    context = ToolContext(dt.datetime(2026, 10, 9, tzinfo=dt.timezone.utc), None)
    reply = agent._run_rounds([{"role": "user", "content": "test"}], context, EvidenceTrace(False), time.monotonic(), lambda value: value)

    assert reply == "ok"
    assert calls == 2
    assert sleeps == [1.0]
