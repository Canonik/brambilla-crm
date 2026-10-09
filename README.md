# Brambilla CRM

A CRM with a HubSpot-compatible API, an English web interface and an Italian-speaking chat
assistant, built for Brambilla Forniture S.p.A. during the Hackitaly 2026 final.

- `server/`: FastAPI service (API, migration from the Sinergia export, business rules, assistant).
- `frontend/`: Vite + React interface (company page, deals board, dormant customers, tickets, assistant).
- `tests/acceptance/`: black-box tests against any deploy; `tests/reference/`: independent
  implementation of the migration rules used to compute expected outcomes.
- `DECISIONS.md`: what the legacy data contains that the requests do not say, and what we do with it.
- `docs/INTEGRATION_CONTRACT.md`, `docs/DEPLOY.md`: how the parts fit and how it ships on Railway.

Run locally: see `docs/INTEGRATION_CONTRACT.md` section 1.
