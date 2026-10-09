# Data & AI status (Agent 2)

Branch `agent/data-ai`, worktree `/tmp/brambilla-data-ai`, base `a6e39d4` (merged main), code commit
`c3b6ecd`. Nothing merged, pushed or deployed by me. No real model calls were made: every scenario
below runs on a scripted model against a local PostgreSQL.

Owned files: `server/app/assistant/attachments.py` (new), additive hunks in
`server/app/assistant/tools.py` and `agent.py` (new methods, new schema entries, prompt lines,
nothing inside `run_tool`), `server/tests/test_assistant_data.py` (new), this file. One hunk in
`server/app/migration/importer.py` (patch 0002 from `agent/score-optimization`, authorised by the
Coordinator at 12:58).

## 1. Data access coverage matrix (assistant tools over the migrated CRM)

| Object | Stored | API-retrievable | Assistant-retrievable | Associations followed | Tested | Missing |
|---|---|---|---|---|---|---|
| companies | yes | yes | `search_companies` (name in any word order, accents and srl/spa ignored, domain, partita IVA, city, class, `id_legacy`), `company_overview`, `revenue`, `deal_stats`, `my_customers`, `dormant_list`, `find_by_legacy_id` | contacts, deals, tickets, activities (overview, `get_record`) | `test_assistant_data.py`, `test_assistant.py` | nothing blocking; `description` only via overview |
| contacts | yes | yes | `search_contacts` (first+last name in any order, email, `company_id`, `id_legacy`), `get_record` | company (`associatedcompanyid`), activities | yes | `hs_additional_emails` only via `get_record` |
| deals | yes | yes | `search_deals` (title, company, contact, pipeline Vendite/Rinnovi, stage label, commerciale by name or email, closedate range, open only, `id_legacy`), `deal_stats`, `revenue` (R8 rule, deterministic), `list_deal_line_items` | companies, contacts, line items, tickets (R10), tasks (R11) | yes | no amount-range filter (totals come from `deal_stats`) |
| tickets | yes | yes | `search_tickets` (subject, company, contact, stage, assegnatario by name or email, priority, open only, `id_legacy`) | contact, company | yes | none |
| products | yes | yes | `search_products` (sku `BF-01234` or `1234`, description), `get_record` | line items | yes | none |
| line_items | yes | yes | `list_deal_line_items`, `get_record`, `import_attachment` | deal, product (`hs_product_id` + 901) | yes | none |
| notes/calls/emails/meetings/tasks | yes | yes | `list_activities` by contact, deal, company, optional year | contact, deal | yes | no free-text search over bodies; no range finer than a year |
| users (utenti.csv) | yes (`crm_users`) | `/crm/v3/owners` | `list_users`, user card in the prompt, names resolved in every follower field | manager, reports | yes | none |
| Clienti dormienti | yes | lists API | `dormant_list` | companies | acceptance | none |
| CSV attachments | request body | n/a | `preview_attachment`, `import_attachment` (all seven Sinergia file kinds, HubSpot headers too) | resolves `id_azienda`, `id_contatto`, `id_opportunita`, `contatti`, `codice_articolo`, `id_utente`/`id_commerciale`, `Da:` header | yes | tasks are not a Sinergia kind |

Everything above reads and writes through `Store`, the same code path as the HubSpot API, so R7, R10,
R11 and R12 fire for the assistant exactly as for API calls (verified in the tests: R10 ticket and
R11 task from a CSV import, R12 company from an email domain, 409 on a duplicate partita IVA).

## 2. R1-R13 correctness risks

- **Migration at `c3b6ecd` on the sample export** (scratch database `brambilla_dataai`, 28.4 s
  end to end, limit is 300 s): companies 17,386, contacts 63,710, deals 33,577, line items 41,014,
  products 1,735, tickets 21,329, activities 359,603 (notes 143,410, calls 107,761, emails 72,232,
  meetings 36,200), associations 1,666,162, dormant 936, classes A 52 / B 25 / C 65,
  `tickets_contact_from_da_line` 456. Identical to the reference oracle figures already
  reconciled this morning; the +92 associations against the 09:30 run are the 46 `Da:` tickets
  of the merged fix, both directions.
- **Patch 0002 (ticket `Da:` header also over `hs_additional_emails`)**: applied cleanly; on the
  sample there are 308 tickets with a `Da:` line and no contact, 45 match a primary email
  (already covered), 0 match only an alias, so zero effect as predicted. Cheap insurance for the
  hidden export.
- **Amounts shaped `12.000` / `12,000`** (one separator followed by exactly three digits) parse as
  a decimal (`12`), per DECISIONS 42, because the sample never writes that shape (0 of 35,020
  rows: every lone separator is followed by 1 or 2 digits). The hidden export comes from the same
  generator, so the risk is low, but a hand-written CSV attachment could use it: the attachment
  tools inherit the rule. Not changed (a decided rule, Core's file).
- **`closedate` when the assistant marks a deal won or lost**: `Store` sets `closedate` only when
  it is empty. Migrated open deals keep `data_chiusura` as the expected close date (13,088 rows),
  so "segna come vinta" leaves that old date instead of `context.now`. HubSpot's default sets the
  close date when a deal enters a closed stage. If the hidden check compares `closedate`, this is
  the most likely mismatch on the example-1 family of requests. Core decision, not touched.
- **R3 through the API**: the HubSpot API accepts any string in `commerciale`/`assegnatario`;
  only the assistant layer now refuses ex-employees and resolves names. Fine for R3 (a migration
  rule) and R13; flagged in case a conformity check expects validation on the API.
- **Evidence trace registry** (`evidence.py`, Agent 4): the new tools `find_by_legacy_id`,
  `search_products`, `preview_attachment` (reads) and `import_attachment` (write, records =
  `created[].id`) plus `list_deal_line_items` from `origin/main` are not in `TOOLS`; see what the
  observer does with unregistered names before relying on the inspector for an import turn.

## 3. Assistant failures found and root causes (state before `c3b6ecd`)

| Failure | Root cause | Status |
|---|---|---|
| CSV attachment: the model had to transcribe Sinergia rows (`nome;cognome;telefono;id_azienda;tipo`, `importo "€ 1.234,56"`, `fase "06 - Vinta"`, `id_commerciale "U29"`) into HubSpot property names by itself; unknown names give `400 PROPERTY_DOESNT_EXIST`, `id_azienda` could not be resolved at all | missing tool | fixed: `preview_attachment`, `import_attachment` reuse the migration normalisers and resolve every Sinergia reference; existing records (same email, partita IVA, sku, `id_legacy`) are never duplicated |
| "il ticket 595833", "l'azienda 264566": nothing searched by `id_legacy`; the hidden scenario is keyed by `id_legacy` | missing tool | fixed: `find_by_legacy_id` + `id_legacy` on the four searches |
| "Mazza Serramenti", "Nicolo" for "Nicolò", "De Luca Maria": substring `ILIKE` on the whole phrase found nothing | wrong tool implementation | fixed: every word in any order, accents and legal suffixes ignored, only as a fallback so exact and substring hits keep priority; ambiguity stays visible (two Mazza companies return `total: 2`) |
| "assegna la trattativa a Luca Santoro" (left the company) or to "Pippo": `update_record` stored any string in `commerciale` | missing validation | fixed: refused before the write with the reason (R3); names and `Uxx` ids become emails; a name shared by an active and an inactive user resolves to the active one (DECISIONS 3) |
| New line items: no `hs_product_id`, deal `amount` untouched | wrong mutation | fixed in the assistant path: `hs_product_id` from the product association, deal amount = total of its lines (R3, HubSpot behaviour). The API path still does not recompute: Core's call |
| OpenRouter `200` with `choices[0].error` or `finish_reason: content_filter` was read as an empty reply; an unexpected exception after a committed write answered "Nessuna modifica è stata apportata" | incorrect final response | fixed in `agent.py`: choice-level errors are model failures; the fallback always lists `ctx.writes`. `admin.py` untouched: its catch-all is now unreachable once the tool context exists |
| Tickets created before `__migrate` (only after a bare `__reset`) fell into the HubSpot default pipeline | wrong default | fixed: Assistenza (and Rinnovi for CSV deals) ensured like R10 does |

## 4. Implemented improvements

All in `c3b6ecd`: `attachments.py` (parser, kind detection, row planner, resolver), nine new or
extended tools in `tools.py`, three prompt lines in `agent.py` (use the attachment tools, legacy
ids, colleague names), `collect_attachments` (attachments from every user turn of the replayed
conversation, not only the last), the failure-path hardening, patch 0002.

## 5. Tests

```
cd /tmp/brambilla-data-ai/server && /home/cano/projects/brambilla-crm/.venv/bin/pytest -q tests -p no:cacheprovider
41 passed in 12.90s
```
`test_assistant_data.py` (14 scenarios): contacts CSV preview then import with legacy company,
R12 and duplicates; preview-only question writes nothing; attachment from an earlier turn;
explicit errors with no or wrong attachment; deals CSV (stages, negative and currency amounts,
inactive commerciale, R10, R11, Rinnovi); products CSV republishing a price (R4); line items CSV
(deal link, product link, deal amount); tickets CSV (Assistenza, priority, `Da:` contact);
activities CSV (types, author, links); `find_by_legacy_id`; company and contact name tokens;
ex-employee refusal and name resolution in writes and searches; choice-level model error;
failure after a write reports the write. The 8 pre-existing assistant tests, the evidence tests
and the smoke tests still pass.

Migration run (sample export, scratch DB): see section 2.

## 6. Branch and commit

`agent/data-ai` at `c3b6ecd` (code) plus this status file. Merge target: main after `a6e39d4`.

## 7. Single highest-value remaining fix

One real-model smoke run on the deployed instance, with Coordinator approval and a hard cap of
four conversations (about $0.10): a CSV import of three contacts, an ambiguous company name,
example 2 (revenue), and a refused request (ex-employee as commerciale). Everything above is
proven with a scripted model; whether GPT-6 Luna picks `preview_attachment`/`import_attachment`
instead of hand-typing `create_records_bulk` is the only thing left unverified, and it decides the
whole "CSV attachment" family of hidden requests. Second: decide `closedate = context.now` when
the assistant closes a deal (section 2).
