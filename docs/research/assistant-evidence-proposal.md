# Assistant Evidence Inspector — Agent 8 proposal

## Verdict

**GO for the isolated passive prototype; NO-GO for production integration now.**
Review snapshot: 2026-10-09 approximately 11:10 Europe/Rome, base `300ea57`.
No shared implementation changed, no model calls, no deployment or production checks.
This is P4; do not delay any R1–R13 work for it.

The cheapest credible feature is a collapsed panel attached to an existing assistant reply,
showing sanitized events from its actual tool dispatcher. No second assistant or model call.
The integration contract already anticipates an execution inspector, so this is a reusable
experiment for the UI owner, not a competing chat implementation.

## Sources and current implementation findings

Read repository `BRIEF.md` (technical rules, assistant contract, model, scoring, rules),
`FAQ.md` (AI feature, credentials, assistant, freeze), `legacy/RICHIESTE.md` R13,
`assistant/examples.md`, `AGENTS.md`, and `docs/INTEGRATION_CONTRACT.md` sections 3, 5–7.
Official local materials are the rules authority; no model pricing assumptions or external
interpretability claims are needed for this zero-call approach.

- Brief: only the chat assistant is allowed; only supplied `openai/gpt-6-luna`, shared $10;
  Italian replies; full conversation supplied each turn; 60 seconds per turn; four concurrent
  conversations; exact organizer response `{"reply":"..."}`. No server conversation state.
- R13: reported actions must exist in CRM and unrelated records must remain unchanged.
- Contract: proposed `POST /ui/api/assistant` uses the same engine and returns `reply, trace`.
  Its trace shape is `step, tool, arguments, result_summary, records[{type,id,label}], ms`.
  **This is a design contract, not evidence of a sanitized implementation.** It lacks explicit
  operation outcome, transaction confirmation and calculation evidence.
- At the base commit there is no `server/` or `frontend/` in main. A read-only look at the
  owners' in-progress worktrees found no assistant dispatcher/route in Core at that instant.
  These observations are transient, uncommitted, and must be rechecked at handoff.
- UI worktree `frontend/src/api/endpoints.ts` currently invokes `/__agente`;
  `frontend/src/api/types.ts` accepts optional loose `trace/tools` with raw input/output fields.
  Its mock returns a synthetic trace. **A fixture is not production provenance.** Do not display
  mock events as live evidence. Do not add trace fields to `/__agente` to satisfy this UI.
- No deployed assistant or critical acceptance pass was verified by this task. That alone
  prevents a production GO. No destructive form check was run.

## Architecture and truthful terminology

Use “behavioral provenance,” “observed operations,” “records observed,” and “commit confirmed.”
Never call this attention inspection, chain of thought, hidden activations, causal attribution,
SAE analysis, or proof of why the model answered. A retrieved record is not necessarily used.

Proposed flow, subject to Coordinator/Core/UI approval:

1. Existing assistant dispatcher executes the same validated CRM service functions.
2. On UI requests only and only when explicitly enabled, a request-local observer records
   dispatcher events. Events never enter model messages or alter tool return values.
3. Core projects an allowlisted, authorized evidence DTO; never send raw arguments/results,
   prompts, credentials, attachments, free-text errors, email addresses or record labels.
4. Existing UI assistant response includes the optional evidence; the panel mounts under
   that reply. No polling, separate database, persistent conversation state or browser storage.
5. `/__agente` still returns exactly `reply`; ideally it never constructs evidence at all.

Observer failures must not cancel/rollback CRM operations, consume the remaining model deadline,
retry a mutation or convert an unknown write into success. Capture status after the real
transaction boundary, not merely when a tool returns. A lost connection at commit is “unknown.”
A rollback must remain distinguishable from an attempt. Any later read-back must be scoped to
an existing authorized operation; do not add reads just for the inspector before freeze.

## Working isolated prototype

Files: `experiments/assistant-evidence/inspector.mjs`, `inspector.test.mjs`, `README.md`.
No dependencies. Exports a pure projection function and a DOM mount function for an existing
chat message container. It is disabled unless passed `enabled: true`. No app entrypoint, chat
engine, HTTP server, model integration, CRM state, or production import is added.

Prototype DTO (a **proposal**, not an implemented backend contract):

```json
{"sequence":1,"tool":"update_record","operation":"write","status":"attempted",
 "records":[{"type":"deals","id":"42"}]}
```

The trusted adapter must map real dispatcher tool identifiers to developer-controlled labels
and operation types. The names above are fixture names, not claims about existing tools.
Read outcomes: attempted/completed/failed. Write outcomes: attempted/committed/rolled_back/unknown.
Monotonic sequence numbers preserve observed order; do not infer causal or database commit order
between parallel tools. Rejected events and capped output are visibly marked partial.

The component retains at most 64 events and 20 record references each, accepts only known CRM
object types and numeric IDs, uses textContent, and discards arbitrary strings. Non-numeric IDs
are omitted with a partial indicator until owners explicitly agree on safe validation.
Authorization still belongs on the server: shape validation cannot authenticate events or
make sensitive record identifiers safe. No record links are added because route support is
not yet verified. No claims of cryptographic audit integrity or permanent history.

No events: “Evidence unavailable … No conclusion about tool use or mutation success can be drawn.”
No calculation inputs: “Calculation evidence unavailable in this prototype.”

## Calculated values and evidence withholding

Do not reverse-engineer a formula from the answer or replay CRM tools. A future approved DTO
could carry a fixed calculation identifier/version, exact decimal result and currency/unit,
context.now, filter/time-window identifier, authorized source record references and input
values, plus an explicit completeness flag. These must come from the actual deterministic
calculation, including discounts/rounding/exclusions used by R8. A stored revenue property
proves a value was read, not that its contributing deals were traced. Partial rows must never
be labeled a complete derivation. Numeric details remain gated by authorization and minimization.

**NO-GO for evidence-withheld response comparison.** Rules do not explicitly authorize this
experiment; another response costs credit, can replay writes and risks deadline/behavior.
Even a read-only replay is not mechanistic or reliable causal evidence. Not implemented or
called. Hiding rows in the panel would only hide display content, not test model dependence.

## Exact integration requirements and gate

Coordinator and each respective owner must approve the exact shared files before work starts.
Suggested ownership boundaries (actual file paths need reinspection):

- Core: existing dispatcher observer and UI-only assistant route. Sanitize before HTTP
  serialization; bind evidence to this request and authorized session, not user email alone.
  `context.user` is task context, not authorization. No global mutable collector. Collect only
  bounded metadata, discard on response, never log payloads. Disabled flag defaults false.
- Coordinator: approve UI-only DTO addition to `docs/INTEGRATION_CONTRACT.md`; confirm production
  flag strategy and freeze time. No new environment variable has been set by this experiment.
- UI: `frontend/src/api/types.ts`, `frontend/src/api/endpoints.ts`, and the actual assistant
  message component, after verifying current paths. Use the approved UI route/same engine;
  never resend a failed write to `/__agente` as a fallback. Mount only on the matching reply;
  clear on logout, reset, new conversation and stale/aborted requests. Keep trace out of the
  messages sent back to the model. Use a default-false explicit feature flag.
- No changes to migrations, schema, database, deployment, or scoring logic are needed.

Release only after Coordinator verifies: critical acceptance tests pass; deployed assistant
works; owner approvals exist; exact `/__agente` JSON is unchanged; off/on modes produce the
same tool calls, model token usage and CRM state; rollback/unknown/authorization/concurrent
conversation isolation pass; unavailable/malformed evidence does not break chat; real-browser
rendering is accessible; safe testing and deployment fit before 15:30. If any gate fails,
leave disabled. Do not change flags, push or deploy after freeze.

## Cost, latency and risk

Measured locally: `node --test experiments/assistant-evidence/inspector.test.mjs` exits 0.
Seven test cases cover default-off behavior, absent evidence, mutation outcomes, sensitive
field filtering, unknown tool/type/order rejection, truncation, request independence and
DOM mounting/cleanup. DOM check uses a minimal fake document, **not browser validation**.
The initial runner reported approximately 56 ms for the whole test file; this is test runtime,
not application latency. No live model/backend/browser performance measured.

Structural facts: prototype makes zero network requests, zero model calls, uses zero model
tokens and zero model credit, and writes no CRM data. Production incremental token cost remains
zero only if evidence is not added to prompts. Local JS executes only when called by a host.

Estimates, not measurements: bounded projection/rendering should be a few milliseconds on a
normal client. A JSON trace could add tens of KB per UI response at the caps; Core must enforce
a serialized byte budget too (suggest 32 KiB with explicit partial status). Default-off and
judge path should incur no observer work. Actual serialization/render times require measurement.

Estimated integration effort: 15–30 minutes UI if sanitized trace already exists; 45–90 minutes
Core plus integration tests if transactional events must be added. These are planning ranges,
not a commitment or reason to distract Core from R13. Backend risk is low while isolated,
moderate if touching the dispatcher. Main hazards: premature commit claims, raw-data leakage,
trace cross-talk, stale per-message evidence, and accidental replay of writes.

## 30-second jury demonstration (conditional on live integration)

0–10 s: In the existing assistant, ask in Italian for a known company's 2025 revenue.
10–20 s: Expand the panel, show actual read event and authorized company ID. Say:
“These are the records our backend observed. This does not expose model internals.”
20–30 s: On an already validated write example, show attempt and confirmed commit, then its
actual CRM record. Say: “We distinguish a requested action from a confirmed database change.”
Do not execute an extra model turn purely to show the panel if credit is scarce. Use the
current live reply. If only this prototype exists, label it “isolated prototype with synthetic
fixtures”; never present it as deployed or as a real observed transaction.

## Coordinator handoff

AGENT: 8 — Interpretability and Evidence Researcher.
BRANCH: `agent/assistant-evidence`; worktree `/tmp/brambilla-assistant-evidence`.
COMMIT: see branch tip / final task handoff (avoids a self-referential commit hash).
VERIFIED WORKING: isolated passive renderer/projection and local tests.
VERIFIED FAILING: no live inspector integration demonstrated; no failing local test.
FILES CHANGED: this proposal and the three experiment files listed above.
TESTS RUN: Node test command above; no production/model requests.
BLOCKERS: sanitized live trace unverified, transaction/calculation semantics absent in shared
contract, deployed assistant/critical tests unverified, shared-file owner approvals absent.
NEXT ACTION: Coordinator may review/cherry-pick research only; recheck owner implementations.
COORDINATOR ACTION REQUIRED: no merge or deploy requested now. Optional integration requires
all gates and explicit exact-file agreement with Core/UI. Keep P0–P2 ahead of this experiment.
