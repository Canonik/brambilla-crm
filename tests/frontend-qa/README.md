# Frontend QA

Read-only preflight, no dependencies:

```sh
python tests/frontend-qa/readiness.py --frontend /path/to/frontend
python tests/frontend-qa/readiness.py --frontend /path/to/frontend --base-url https://your-deployment
```

Returns nonzero for missing entry files, invalid health metadata, unavailable routes,
or missing React HTML shells. This does not execute JavaScript, authenticate, inspect
CRM data, validate accessibility or certify browser workflows. See
`docs/reviews/frontend-audit.md` for the browser checklist and current evidence.
Do not confuse a passing preflight with a passing integration test.
