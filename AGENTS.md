# BRAMBILLA CRM — SHARED PROJECT HANDOFF

**Event:** Hackitaly 2026 CRM Final  
**Deadline:** 2026-10-09, 15:30 Europe/Rome — production freeze  
**Goal:** Maximize objective judge score first, then compete on product/UI among the six highest-scoring projects.  
**Repository:** `brambilla-crm` (new, originally an empty application repo; supplied starter documentation/data only).

> This file is the common source of coordination context for all three agents. The official challenge files are the authoritative specification. If this handoff disagrees with `BRIEF.md`, `FAQ.md`, or `legacy/RICHIESTE.md`, the official files win. Do not infer request/response schemas from this summary.

## 1. Challenge and scoring

Build a usable CRM that exposes an API compatible with the specified HubSpot CRM behavior, imports all fifteen years of data from Brambilla Forniture S.p.A.'s legacy CRM, and supports a **single in-product AI feature: the chat assistant**, using the supplied model/key.

| Component | Automatic points | What matters |
|---|---:|---|
| R1–R12, Brambilla requests | 50 | Correct observable CRM state/behavior after migration and operations |
| R13, AI assistant | 30 | Robust answers/actions across ~40 unseen conversations |
| API conformity | 10 | Documented HubSpot-compatible semantics and responses |
| Durability | 10 | Data persistence, concurrency, no dropped or lost records |

The English UI has **no automatic tests**. Among the top six by automated test score, the jury evaluates the company page, deals board, dormant customers list, tickets, choices sheet, and overall product. Final ranking among those six is **80% test score / 20% jury**. Do not confuse UI score with the 100-point automated score.

## 2. Source of truth — read before implementing

- `BRIEF.md`: exact technical contracts, authentication, endpoints, deployment instructions.
- `FAQ.md`: official clarifications; resolves ambiguities.
- `legacy/RICHIESTE.md`: business requirements R1–R13.
- `assistant/examples.md`: assistant contract examples (illustrative, not exhaustive).
- `legacy/export.zip`: provided legacy dataset; hidden data will also be evaluated.
- `CHOICE-SHEET.md`: required discussion of ambiguous/underspecified business decisions.

Read all docs and inspect the actual archive and nested schema. Never assume hidden data equals sample data. Validate any speculative assumptions against authoritative files.

### Organizer-facing endpoints

The judge's **form check** exercises `/health`, `/__reset`, `/__migrate`, `/__agente`, deployment reachability, model-key/token acceptance, and sample tests. Implement the **exact request, response, authentication, and status code contracts in `BRIEF.md`**; these endpoint names alone are insufficient to infer their schemas. The form check is **not** the full suite or a score estimate.

- Form check: https://final.hackitaly.ai/form-check
- Choices: https://final.hackitaly.ai/choices (fill between 15:00 and 15:30)
- Freeze: 15:30; **no push, redeploy, or changed environment variables afterward**.
- Ranking: 16:30. Top 3 give an 8-minute pitch.

## 3. Team and ownership (three Codex sessions, separate worktrees)

| Agent | Branch/worktree | Owns | Must not do |
|---|---|---|---|
| Coordinator | `main` / `~/projects/brambilla-crm` | `AGENTS.md`, `docs/INTEGRATION_CONTRACT.md`, root deployment/CI/tests, Railway, merges, `DECISIONS.md`, form checks, choices | Reimplement worker features unnecessarily |
| Core / Evaluation | `agent/core` / `~/projects/brambilla-core` | `server/`: schema, migration, R1–R13 logic, API endpoints, GPT-6 assistant, backend tests and API docs | Touch `frontend/`, deploy production, push to `main` |
| UI / Product | `agent/ui` / `~/projects/brambilla-ui` | `frontend/`: English UI, company page, deals board, dormant customers, tickets, chat UI, frontend tests | Touch `server/`, root deploy files, push to `main` |

Coordinator is the **sole integration/deployment owner**. Worker agents commit frequently on their own branches. Coordinator integrates commits incrementally. Worktrees see **committed** branch state, not unsaved changes in another worktree. When coordinator updates this document or the shared contract on `main`, workers must retrieve it using `git show main:AGENTS.md` and `git show main:docs/INTEGRATION_CONTRACT.md` or merge/rebase `main` carefully.

**Priority rule:** ~90% of technical effort should maximize functional correctness of score-bearing paths. The UI runs in parallel with its own dedicated agent. Do not stall core tasks on visual polish.

## 4. Shared integration contract (Coordinator must publish early)

Write `docs/INTEGRATION_CONTRACT.md` as soon as authoritative docs are parsed. It must specify:

1. Chosen backend/frontend framework and app start commands; same-origin/proxy strategy for local and production use.
2. Backend API base path, auth/token handling, exact schema pointers, errors, pagination, filtering, and CRM object relationships.
3. UI routes and **real** endpoints consumed; no invented production API shapes.
4. Assistant endpoint shape/session/state handling as specified, and how the UI invokes it.
5. PostgreSQL `DATABASE_URL` configuration, migration source location, other environment variable names (never secrets).
6. Healthchecks, port binding (`0.0.0.0:$PORT` if appropriate for chosen runner), deployment entrypoint, tests.

Changes to shared contracts must be communicated in commits. Backend supplies `server/API_FOR_UI.md` with implemented routes; UI uses a centralized typed API client and does not hardcode mocks in production.

## 5. Core correctness policies

- **Migration:** Parse the real legacy data format and preserve all required records, fields, IDs, associations, timestamps, notes, histories, and tickets according to the brief. Handle hidden export, malformed/missing/null fields, duplicates, missing references and reruns as specified. No silent loss. Check import summaries/counts and integrity.
- **Persistence:** Use an actual persistent store, preferably Railway PostgreSQL if the brief permits. No reliance on Railway's ephemeral app filesystem for authoritative CRM state. Transactional writes, safe concurrent operations, predictable reset/migration behavior.
- **API:** Implement documented HubSpot-compatible behaviors rather than only matching route names. Validate IDs, query operators, pagination, associations, error status/shape, and authorization against the official docs. Cover examples with executable tests.
- **Business rules:** Translate R1–R12 into acceptance tests. Prioritize end-state correctness and edge cases. Record every assumption about underspecified scenarios in `DECISIONS.md`.
- **Assistant:** Only supplied GPT-6 Luna model/key and only AI feature in CRM. Must use typed, validated backend tools and the same authoritative data source as API/UI. Deterministic computations in code; never hallucinate a write. Test unknown/unseen user requests, ambiguity, context carryover if specified, and failure handling. Respect given budget and quotas. Never log or commit secrets.
- **UI:** English, no HubSpot brand name or logo visible; ship company page, deals board, dormant customers list, tickets, and integrated assistant. Real data and clear empty/loading/error states. Once usable, refine visual design for jury.
- **Mech-interp-inspired twist:** Optional, last priority. Inside assistant UI, expose tool-call provenance, retrieved evidence, or action trace if available. This is *behavioral provenance*, **not** access to hidden model activations; do not claim activation patching or SAE analysis. Never build a separate AI feature.

## 6. Engineering workflow and handoffs

Each worker should produce working vertical slices and commit at every milestone. Suggested commit stages:

- Core: service skeleton → migration → CRM API → R1–R12 → assistant → hardening.
- UI: Vite shell/navigation → company/deals/dormant/tickets → assistant integration → polish.
- Coordinator: contract & basic deployment → initial merge/deploy → form check → iterative fixes → freeze.

After each worker milestone, update its handoff (`server/HANDOFF.md` or `frontend/HANDOFF.md`) with: implemented items, run/build commands, routes/schema or missing dependencies, tests run and results, known failing cases, and commit hash.

Coordinator should **merge early and often**, run smoke/integration tests, and deploy a functional skeleton as soon as it exists. Example branch inspection: `git log --oneline agent/core -5`, `git log --oneline agent/ui -5`. Avoid long-running uncommitted integration changes.

## 7. External feedback loop and prioritization

1. Deploy the smallest compliant skeleton as early as possible.
2. Run organizer's **form check** against the public Railway deploy.
3. Inspect request/response mismatch details and compare to exact contracts.
4. Fix the highest-value failure category, add regression test, commit, merge, deploy, recheck.
5. Repeat until freeze. Distinguish pass of form check from full benchmark quality.
6. Ensure migration is tested end-to-end *on deployed infrastructure*, not just locally.
7. Confirm secret/token variables, persistent DB, application restart, concurrency behavior and deployed health.

Prefer deterministic correctness > assistant breadth > UI polish except when a high-severity integration/availability failure blocks everything. Avoid spending extensive time on speculative optimizations or local-only demos.

## 8. Schedule (Europe/Rome, hard deadline)

- **10:30–11:00:** Read specs, initialize repo/worktrees, publish integration contract, build deployable skeleton.
- **11:00–12:00:** First Railway deployment, PostgreSQL, migrate and core CRUD/API; first form check.
- **12:00–13:00:** R1–R12 correctness and score-bearing acceptance tests; UI screens build in parallel.
- **13:00–14:00:** Assistant tools and chat; combine live backend and real UI.
- **14:00–15:00:** Regression checks, edge cases, API conformity, durability, form-check fixes.
- **15:00–15:30:** Complete **Choices** sheet, validate production URL, final deployment; freeze at **15:30**.

These are targets, not permission to omit necessary features. Timeboxing and fast feedback matter more than perfection.

## 9. Railway release criteria

Coordinator owns Railway project and service, attached private GitHub repo, PostgreSQL, environment references (not committed secrets), domain, build config, and public URL. Verify `GET /health` with exact expected output; then reset/migrate/assistant checks with authorized test requests, observing their side effects. Validate latest commit is deployed and remains frozen after 15:30.

## 10. Decision and issue reporting

Maintain `DECISIONS.md` with issue, evidence from data, chosen behavior, alternatives, tradeoff, and status; use this to answer the choices sheet. Distinguish observed data anomalies from guesses. Do not manufacture missing business facts. `docs/INTEGRATION_CONTRACT.md` owns inter-agent interface decisions; this document owns common mission and priorities.

### Immediate launch sequence

1. Coordinator: parse source-of-truth files and publish/commit integration contract.
2. Core: inspect export and begin backend skeleton + migration simultaneously.
3. UI: build an English CRM shell using a replaceable API adapter.
4. Coordinator: provision Railway + PostgreSQL and prepare service deployment.
5. All agents: commit usable milestones; Coordinator integrates and tests continuously.

**Final principle:** Optimize what the evaluator can observe. No cosmetic feature compensates for a failed migration, noncompliant endpoint, or assistant unable to modify the CRM correctly.
