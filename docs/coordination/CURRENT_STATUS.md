# Current status (shared, edited only by the Coordinator)

Updated: 2026-10-09 12:55 Europe/Rome. Freeze: 15:30. Production:
https://faithful-emotion-production-1fe1.up.railway.app (Railway project final-alessandro-canoni-b32bfd,
auto-deploys every push to `main`).

Workers never edit this file. Each worker keeps its own file in this directory on its own branch:
`ui-status.md`, `data-ai-status.md`, `backend-status.md`, `interpretability-status.md`.

## Releases

| Commit | Pushed | Railway | Verified in production | Verdict |
|---|---|---|---|---|
| 75d0043 | 12:32 | success | /health 200, SPA served, 401 without token | previous release, no authenticated checks run by the current coordinator |
| a6e39d4 | 12:52 | success 12:53 | /health 200, SPA bundle hash matches local build, 401 without token | `hackitaly-good-001` (authenticated production checks still pending the token) |

Local evidence on a6e39d4 (server on 127.0.0.1:8040, database `brambilla_release`):
`server/tests` 26 passed; `tests/acceptance/test_form_check.py` + `test_api_conformity.py` 26 passed;
`test_migration.py` + `test_rules_behavior.py` 32 passed (migration 26.9 s locally); `npm ci && npm run build` exit 0.

Known-good tags: `hackitaly-good-001` = a6e39d4. Convention `hackitaly-good-NNN` on `main`.

Blocked: authenticated production checks and the Railway CLI. Needs the human to run
`railway login` or to put `CRM_TOKEN` and `OPENROUTER_API_KEY` in `~/.brambilla-secrets.env`.

## Team

| Agent | Role | Session | Branch / worktree | HEAD | Objective | Owns | Pending merge |
|---|---|---|---|---|---|---|---|
| 1 | AI-first UI architect | brambilla-crm-14 | `agent/ui-architect` ~/projects/brambilla-ui-architect | 04c3c32 (rebase to a6e39d4) | premium shell, dashboard, assistant drawer, deals board motion | `frontend/` (index.css, App.tsx, AppShell, Dashboard, AssistantChat, AssistantDrawer, DealsBoard, components/motion, components/command) | first handoff 13:30 |
| 2 | Data and AI intelligence | brambilla-crm-74 | `agent/data-ai` /tmp/brambilla-data-ai | 04c3c32 (rebase to a6e39d4) | CSV attachment import tool, id_legacy lookup, SKU search, name matching, active-user check before writes | `server/app/assistant/attachments.py`, additive hunks in `tools.py` and `agent.py`, `server/tests/test_assistant_data.py` | first handoff 13:20 |
| 3 | FastAPI reliability | brambilla-crm-21 | `agent/backend-reliability` /tmp/brambilla-backend | 4273767 (rebase to a6e39d4) | durability, concurrency, search totals, R7/R10/R11/R12 via API, conformity details | `server/app/*.py` except assistant and migration, `server/app/routers/*`, `server/tests/*` except assistant tests | every 20 min |
| 4 | Assistant interpretability | brambilla-crm-b3 | `agent/assistant-insights` /tmp/brambilla-assistant-insights | 04c3c32 (rebase to a6e39d4) | Assistant Insights inspector on the existing evidence trace | `server/app/assistant/evidence.py`, `test_assistant_evidence.py`, `frontend/src/assistant/EvidenceInspector.tsx`, `evidence.ts`, `insights/*` | by 14:30, last merge window |
| 5 | Coordinator | brambilla-crm-96 | `main` ~/projects/brambilla-crm | a6e39d4 | integration, releases, production, choice sheet | `docs/`, `AGENTS.md`, `DECISIONS.md`, root deploy files, `tests/acceptance`, `tests/reference` | n/a |
| helper | oracle and choice sheet | brambilla-crm-e7 | `main` (same worktree, read-only except `docs/CHOICE_SHEET_DRAFT.md`) | a6e39d4 | final choice sheet text by 14:30 | `docs/CHOICE_SHEET_DRAFT.md` (does not commit) | n/a |

Older worktrees (`agent/core`, `agent/ui`, `agent/creative-ui`, `agent/frontend-qa`, `agent/backend-audit`,
`agent/score-optimization`, `agent/assistant-eval`, `agent/challenge-intelligence`, `coordinator/release`,
`agent/llm-performance`) are frozen inputs: their unmerged commits are reviewed by the Coordinator, nobody
builds on them. A non-Claude session has committed to `main` from the Coordinator's worktree as late as
12:50 (1637de1, screenshots only): it must stop.

## Requirements coverage

Legend: PASS = test evidence on a6e39d4; PROD = verified on production; UNTESTED = no evidence yet.

| Requirement | Points | Owner | Implementation | Local tests | Production evidence | Risk |
|---|---|---|---|---|---|---|
| R1 companies | 4 | 2 | migration, dedup by domain, `hs_additional_domains` | `test_migration.py` PASS 12:55 | none (needs token) | medium: hidden export shapes |
| R2 contacts | 4 | 2 | migration, dedup by email and by name in company | `test_migration.py` PASS 12:55 | none | medium |
| R3 deals | 6 | 2 | migration, line-item totals, active commerciale | `test_migration.py` PASS 12:55 | none | medium |
| R4 products and line items | 4 | 2 | migration | `test_migration.py` PASS 12:55 | none | low |
| R5 tickets | 4 | 2 | migration, `Da:` fallback | `test_migration.py` PASS 12:55 | none | low |
| R6 activities | 4 | 2 | migration into notes, calls, emails, meetings | `test_migration.py` PASS 12:55 | none | low |
| R7 partita_iva unique, 409 | 4 | 3 | `rules.py`, partial unique index | `test_rules_behavior.py` PASS 12:55 | none | low |
| R8 fatturato_2025 and class | 6 | 2 | computed at migration | oracle match 100 percent on sample (11:35) | none | medium: only post-migration, not recomputed on edits |
| R9 dormant list | 4 | 2 | static list at migration | 936/936 on sample | none | low |
| R10 won deal ticket | 4 | 3 | `rules.py` on stage transition | `test_rules_behavior.py` PASS 12:55 | none | low |
| R11 lost deal task | 3 | 3 | `rules.py` | `test_rules_behavior.py` PASS 12:55 | none | low |
| R12 contact finds company | 3 | 3 | `rules.py` on create and email change, migration | `test_rules_behavior.py` PASS 12:55 | none | low |
| R13 assistant | 30 | 2 (tools), 5 (verification) | OpenRouter tool loop, 19 tools, evidence observer off by default | `server/tests/test_assistant.py` scripted model, 26 passed | none; real-model end-to-end never run by this coordinator | HIGH: untested against the real model and the organizer flow |
| API conformity | 10 | 3 | HubSpot v3/v4 shapes, date-versioned contacts route | `test_api_conformity.py` 26 passed | 401 envelope PROD | medium |
| Durability | 10 | 3 | PostgreSQL, metadata preserved on restart (77c1f22) | `test_durability_local.py` PASS 12:55, restart test on agent/score-restart-fix | none | medium: Railway latency under 20 readers unmeasured |
| Jury: UI | 20 percent of top 6 | 1 | SPA at `/companies`, `/deals`, `/dormant`, `/tickets`, `/assistant` | vitest, build | SPA loads PROD | medium |
| Jury: choice sheet | with UI | 5, helper e7 | `docs/CHOICE_SHEET_DRAFT.md` | n/a | n/a | fill 15:00 to 15:30 |

Gaps nobody owned before 12:50, now assigned: real-model end-to-end assistant test on production
(Coordinator, needs token and explicit authorization since it spends model budget); production restart
and 20-reader latency measurement (Agent 3 locally, Coordinator on Railway after token).

## Log

- 12:45 Coordinator takeover. `origin/main` 75d0043 deployed; local `main` 04c3c32 diverged.
- 12:51 Merge of 75d0043 into main (conflict in `run_tool` resolved keeping writes rollback and observer): a6e39d4.
- 12:52 Pushed a6e39d4; Railway success 12:53; health, SPA and 401 verified.
- 12:55 Migration and rules suites 32 passed on a6e39d4; tagged `hackitaly-good-001`.
