# Backend status (Agent 3, backend reliability)

Branch `agent/backend-reliability`, worktree `/tmp/brambilla-backend`. Updated by Agent 3 only.
Local server for evidence: port 8030, database `brambilla_agent3` (nobody else uses it).

## 13:15

All on `agent/backend-reliability`, full backend suite 202 passed (`cd server && DATABASE_URL=...scratch_db CRM_TOKEN=test-token python -m pytest -q tests`).
Acceptance on my migrated server (port 8030): form_check + api_conformity + migration + rules 56 passed.

| Commit | What | Regression test |
|---|---|---|
| 2a9e099 (in main 6257d93) | 141 5xx from malformed bodies and ids now 400/404 | test_malformed_input.py |
| f7d5273 (in main) | every 2026-09 dated URL family | test_dated_routes.py |
| c9b5dcc | rate limit default 50000 per 10 s (20 readers got 429 on 88 percent of reads) | test_rate_limit.py |
| 1bceac5 | exports: 202, filterGroups, sorts, query, status timestamps | test_exports_conformity.py |
| e4776bc | NaN/Infinity 400, HALF_UP money, default quantity amount | test_numbers.py |
| dd1d118 | hasUniqueValue enforced for custom properties (partial unique index) | test_unique_properties.py |
| ce68ed1 | closedate stamped on entering a closed stage; create into closed was never persisted | test_deal_close_date.py |
| next | recordsIdsAdded, mappedObjectTypeIds, import robustness | test_lists_imports_shape.py |

Next: concurrency on one record and upserts, search and pagination on the migrated volume, 20-reader latency with the new limit, restart end to end.
