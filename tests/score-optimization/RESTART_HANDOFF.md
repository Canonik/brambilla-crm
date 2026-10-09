# Restart metadata fix — implemented and verified

Branch: `agent/score-restart-fix`, based on current main `3eef9eb`.
Worktree: `/tmp/brambilla-score-restart-fix`.

The user's "ok go" authorized the next action proposed in the optimizer report:
implement the existing startup-metadata preservation repair and verify restart/reset.
This focused branch adopts Backend Auditor's
`05-restart-on-core-2dc3c35.patch`; no other optimizer candidates are included.
Core's worktree, main, and production remain untouched. Coordinator owns final merge/deploy.

## Change

- `server/app/defaults.py`: startup inserts missing default metadata using
  conflict-safe inserts and retains existing custom definitions, groups, pipelines,
  association labels, timestamps, and edits to defaults.
- `server/app/routers/admin.py`: `/__reset` explicitly requests destructive default
  reseeding, preserving the documented fresh-account reset behavior.
- `tests/score-optimization/test_restart_reset.py`: isolated PostgreSQL tests cover
  repeated startup, exact metadata preservation, edited defaults, repeated reset,
  cleared records/lists/custom metadata, restored defaults and rate counters.
- `tests/score-optimization/api_volume_benchmark.py`: reproducible real-process
  migration/restart/reset check using a private schema, loopback-only HTTP, an
  immutable source copy, and cleanup of its own process/schema.

## Evidence

| Check | Result |
|---|---|
| New startup regression against unmodified Core `2dc3c35` | Fails, confirming the regression detects the original bug |
| Focused startup/reset regressions against fixed branch | 2 passed in 1.82 s |
| Existing Backend Auditor mocked-assistant restart regression | 1 passed in 1.06 s; won-deal write creates correctly associated supply ticket |
| Full supplied export through actual HTTP migration | 204 in 28.338 s; 538,354 objects, 1,666,162 association rows, 936 dormant members |
| Twenty clients, 200 reads | 200 correct responses; p95 53.758 ms; no reads over one second |
| Actual uvicorn process restart | All record counts, nine `id_legacy` definitions, unique VAT definition, Rinnovi/Assistenza pipelines and dormant list preserved |
| Full-volume reset after restart | 204, empty body, 0.2638 s; no objects/associations/memberships/custom definitions/lists; only default pipelines remain |

Raw evidence is in `restart_reset_verified.json` and its log. Source hashes identify
the tested files; the report's Git SHA is the branch base because it was captured
before this fix was committed. Its `tracked_backend_clean: false` is expected.
All local test schemas and server processes were removed by their fixtures.
No model calls, organizer checks, production resets, merges or deployments occurred.
Local timing does not establish Railway timing or an official score.

## Reproduce

From this worktree, with the existing Core Python environment:

```bash
SCORE_DATABASE_URL=postgresql://brambilla:brambilla@127.0.0.1:5433/brambilla \
  /home/cano/projects/brambilla-core/server/.venv/bin/python -m pytest -q \
  tests/score-optimization/test_restart_reset.py

SCORE_SERVER_ROOT=/tmp/brambilla-score-restart-fix/server \
SCORE_DATABASE_URL=postgresql://brambilla:brambilla@127.0.0.1:5433/brambilla \
  /home/cano/projects/brambilla-core/server/.venv/bin/python \
  tests/score-optimization/api_volume_benchmark.py --export legacy/export.zip \
  --output /tmp/restart-reset-recheck.json --restart --reset
```

Remaining dependency: Coordinator integrates this branch's fix and validates the
restart/reset behavior on the deployment it owns. The six other optimizer patch
candidates remain separate on `agent/score-optimization` for subsequent review.
