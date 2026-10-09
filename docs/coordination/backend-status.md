# Backend status (Agent 3, backend reliability)

Branch `agent/backend-reliability`, worktree `/tmp/brambilla-backend`. Updated by Agent 3 only.
Local server for evidence: port 8030, database `brambilla_agent3` (nobody else uses it).

## 12:52

- HEAD 4273767: restart keeps migrated metadata (same hunk as 77c1f22 on origin/main), new
  regression test `server/tests/test_restart_metadata.py`.
- Verified on local main 04c3c32 before any change: `tests/acceptance/test_form_check.py` +
  `test_api_conformity.py` 24 passed, `server/tests` 24 passed. The historical form-check
  failures (404 on `/crm/objects/2026-09/contacts`, 405 on create, `id_legacy`) are fixed and
  the date-versioned routes are in production's `/__openapi.json`.
- In progress: migration + rules baseline, 500 sweep with malformed inputs, unique custom
  properties, 20-reader latency on the migrated volume, restart end to end.

## Owned files

`server/app/{main,config,db,errors,store,search,defaults,rules,util,pipelines,brambilla}.py`,
`server/app/schema.sql`, `server/app/routers/*`, `server/tests/*` except `test_assistant*.py`.
Not touched without Agent 2: `server/app/assistant/*`, `server/app/migration/*`. Never `frontend/`.
