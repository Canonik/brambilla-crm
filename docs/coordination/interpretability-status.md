# Assistant Insights 2 status

Branch `agent/insights-2`, worktree `/tmp/brambilla-insights-2`, based on main `a354aea`.
Implementation commit: `7e04db1` (`feat: add grounded assistant decision insights`).

## Handoff: ready with one coordinator-owned wiring line

The implementation is contained in the owned files and is green. Grounding needs the final reply,
but `server/app/assistant/agent.py` is explicitly outside this agent's ownership. In that file,
change the traced branch of `finish` from:

```python
observer.snapshot()
```

to:

```python
observer.snapshot(reply)
```

This runs only for `?trace=1`; the bare response stays exactly `{"reply": "..."}` and does not
perform fact extraction. Decision paths already work without this wiring because they are derived
from the observed tool calls.

## Shipped

- Grounding extracts bounded candidate amounts, CRM ids, emails, dates and record names from the
  final reply, compares normalized values with this turn's tool outputs, and emits only the matched
  strings plus the supporting event number. Unmatched candidates are marked `unverified`.
- Every requested write tool emits a bounded decision path: preceding completed reads, candidate
  count, chosen record, a fixed plain-English action, and R10/R11/R12 automation record references.
- The inspector starts with one plain-English outcome sentence and numbered steps. Named records are
  clickable chips. Saved changes use a green check; unverified facts use amber. Durations, event ids,
  raw status badges and the compact technical decision chain are behind `Details`.
- Trace validation remains fail-closed, request-local and capped at 32 KiB. Raw tool payloads,
  prompts, arbitrary errors and credentials are not serialized. No model call was added.
- Keyboard tabs and toggles remain accessible. Existing global `prefers-reduced-motion` handling
  covers the additions; the new narrative itself has no animation.

## Files changed

- `server/app/assistant/evidence.py`
- `server/tests/test_assistant_evidence.py`
- `frontend/src/assistant/EvidenceInspector.tsx`
- `frontend/src/assistant/evidence.ts`
- `frontend/src/assistant/evidence.test.ts`
- `frontend/src/assistant/insights/AssistantInsightsAdditions.test.tsx`
- `frontend/src/assistant/insights/DecisionPath.tsx`
- `frontend/src/assistant/insights/Grounding.tsx`
- `frontend/src/assistant/insights/Narrative.tsx`
- `frontend/src/assistant/insights/RecordRef.tsx`
- `frontend/src/assistant/insights/Timeline.tsx`
- `docs/screenshots/assistant-insights/10-grounding-decision-path.png`
- `docs/screenshots/assistant-insights/11-grounding-details.png`
- `docs/coordination/interpretability-status.md` (this handoff commit)

## Verification

Scratch database created as requested:

```text
docker exec brambilla-pg psql -U brambilla -d brambilla -c "create database brambilla_insights2"
```

Backend, using the repo virtual environment because the system interpreter lacks `psycopg`:

```text
cd server && DATABASE_URL=postgresql://brambilla:brambilla@127.0.0.1:5433/brambilla_insights2 \
  CRM_TOKEN=test-token /home/cano/projects/brambilla-crm/.venv/bin/python -m pytest -q \
  tests/test_assistant_evidence.py tests/test_assistant.py
# 22 passed in 2.65s
```

Frontend:

```text
cd frontend && npm run typecheck && npx vitest run && npm run build
# typecheck passed; 8 test files / 64 tests passed; production build passed
```

No real model call or model key was used.

## Screenshots

- [Plain outcome, grounding and numbered decision steps](../screenshots/assistant-insights/10-grounding-decision-path.png)
- [Details expanded with event ids, statuses, durations and decision chain](../screenshots/assistant-insights/11-grounding-details.png)

Screenshots were captured in local Chromium with reduced motion and a scripted sanitized trace; no
production service or model was contacted.
