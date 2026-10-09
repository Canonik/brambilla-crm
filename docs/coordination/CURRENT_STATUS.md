# Current status (shared, edited only by the Coordinator)

Updated: 2026-10-09 13:20 Europe/Rome. Freeze: 15:30. Production:
https://faithful-emotion-production-1fe1.up.railway.app (Railway project final-alessandro-canoni-b32bfd,
auto-deploys every push to `main`).

Workers never edit this file. Each worker keeps its own file in this directory on its own branch:
`ui-status.md`, `data-ai-status.md`, `backend-status.md`, `interpretability-status.md`.

## Releases

| Commit | Pushed | Railway | Verified in production | Verdict |
|---|---|---|---|---|
| 75d0043 | 12:32 | success | /health 200, SPA served, 401 without token | previous release, no authenticated checks run by the current coordinator |
| a6e39d4 | 12:52 | success 12:53 | /health 200, SPA bundle hash matches local build, 401 without token | `hackitaly-good-001` (authenticated production checks still pending the token) |
| 78feee0 | 13:17 | success 13:18 | authenticated read-only check 13:18: stats, legacy and dated reads, search totals equal to the oracle, pipelines, dormant list, owners, properties, labels, SPA routes; 40 parallel reads p95 0.24 s | `hackitaly-good-002`: assistant CSV tools, insights inspector, new UI; local unit 196, acceptance 65, vitest 60 |
| 2694c78 | 13:07 | success 13:08 | /health 200, bundle unchanged, 401 without token | dated route families, 4xx on malformed input, rate limit 50000/10 s; local: unit 176, form+conformity+dated 33, migration+rules 32 |

Local evidence on a6e39d4 (server on 127.0.0.1:8040, database `brambilla_release`):
`server/tests` 26 passed; `tests/acceptance/test_form_check.py` + `test_api_conformity.py` 26 passed;
`test_migration.py` + `test_rules_behavior.py` 32 passed (migration 26.9 s locally); `npm ci && npm run build` exit 0.

Known-good tags: `hackitaly-good-001` = a6e39d4, `hackitaly-good-002` = 78feee0. Convention `hackitaly-good-NNN` on `main`.

Credentials: `~/.brambilla-secrets.env` holds `CRM_TOKEN` and `OPENROUTER_API_KEY` since 13:18 (never committed). Railway CLI stays logged out (GitHub 2FA failed); deploy status comes from the GitHub commit status and the bundle hash.

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

## Open defects (ranked by points at stake, from the 12:57 audit reconciliation)

| # | Defect | Area | Status on a6e39d4 | Owner | Due |
|---|---|---|---|---|---|
| 1 | FIXED in 2694c78 (f7d5273). Dated `2026-09` URL families were missing for pipelines, lists, owners, imports, exports, association batches and record associations (only objects and properties aliased). `tests/acceptance/test_dated_routes.py`: 5 of 7 fail. The organizer form check uses dated URLs. | conformity 10, possibly R9 reads | FIXED, deployed | Agent 3 | done 13:07 |
| 2 | `/__agente` catch-all claims no changes even when earlier tool calls committed; choice-level model errors ignored | R13 quality | FIXED in 3e02c1c (c3b6ecd) | Agent 2 | done |
| 3 | Export create 200 instead of 202; VIEW export ignores `filterGroups` and sorts | conformity | OPEN | Agent 3 | after 1 |
| 4 | `Infinity` raises, `NaN` stored; `fmt_money` HALF_EVEN vs migration HALF_UP; line item without quantity gets no `amount` (patch 03 on agent/backend-audit) | conformity, R13 maths | OPEN | Agent 3 | after 1 |
| 5 | `hasUniqueValue` not enforced for API-created custom properties (R7 itself safe via index) | conformity | OPEN | Agent 3 | after 1 |
| 6 | `recordIdsAdded` spelling (docs: `recordsIdsAdded`); import response lacks `mappedObjectTypeIds` | conformity | OPEN | Agent 3 | after 1 |
| 7 | Ticket `Da:` fallback does not look at `hs_additional_emails` (patch 0002 on agent/score-optimization) | R5 hedge | FIXED in 3e02c1c | Agent 2 | done |
| 9 | closedate not set when a deal enters a closed stage via API or assistant (HubSpot sets it) | R13 operations | OPEN, decided 13:08 | Agent 3 | 13:45 |
| 8 | Empty pipeline with `r1..r4` stage maps to Rinnovi while RICHIESTE says no pipeline means Vendite; zero rows in sample | R3, choice sheet | UNCLEAR, documented | Coordinator | choice sheet |

Fixed since the audits (verified in code on a6e39d4): restart metadata loss (77c1f22), CSV delimiter hard-coded to `;`,
assistant pipeline and stage targeting plus rollback ledger (75d0043), search hardening and local calendar date (046b7f8),
tickets with a dead contact reference use the `Da:` line.

## Log

- 12:45 Coordinator takeover. `origin/main` 75d0043 deployed; local `main` 04c3c32 diverged.
- 12:51 Merge of 75d0043 into main (conflict in `run_tool` resolved keeping writes rollback and observer): a6e39d4.
- 12:52 Pushed a6e39d4; Railway success 12:53; health, SPA and 401 verified.
- 12:55 Migration and rules suites 32 passed on a6e39d4; tagged `hackitaly-good-001`.
- 12:59 Dated-route acceptance test added (ca79381): 5 of 7 families fail; assigned to Agent 3 as P0.
- 13:07 Release 2 pushed (2694c78): dated routes, malformed input 4xx (141 former 500s), rate limit 50000/10 s. Railway success 13:08.
- 13:10 Merged agent/data-ai 1cc3c8f, agent/assistant-insights 932870b then ea36560, agent/ui-architect 8823190 (3e02c1c). Full check: unit 196, acceptance 65, vitest 60, clean npm ci build ok.
- 13:10 Human started an organizer form check on production (release 2); earlier checks today: 11:53 4/6, 12:10 4/6, 12:34 5/6 (failing item unknown to the coordinator).
- 13:17 Release 3 pushed (78feee0); Railway success 13:18; authenticated production checks pass; tagged `hackitaly-good-002`.
- 13:19 Merging agent/backend-reliability 9e716c7 for release 4; full check running.
- 13:20 Production migration timing read from /__stats: the 13:10 organizer form check migrated the sample export in 30.9 s on Railway (build 17.3, copy 5.8, indexes 4.9); 538,354 records, 1,666,162 associations, 936 dormant, classes A 52 B 25 C 65, identical to the oracle.
