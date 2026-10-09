# Decisions

What the Sinergia export contains that the requests do not say, how the CRM handles it, and
why. Every rule below was measured on the sample export (`legacy/export.zip`, 1 December 2026)
with the scripts in `tools/analysis/` (`python3 -I tools/analysis/profile.py <dir>` etc.).
The hidden export follows the same rules with different data, so rules are written for shapes,
never for specific values. Status: `decided` means implemented or to implement as written;
`open` means still to confirm.

Legend of files: `aziende.csv` (companies), `contatti.csv` (contacts), `opportunita.csv`
(deals), `righe_offerta.csv` (quote lines), `listino.csv` (price list), `ticket.csv`,
`attivita.csv` (activities), `utenti.csv` (users), `storico_fasi.csv` (stage history).
All nine: `;` separator, Windows-1252, header row, quoted multi-line text fields.

## 0. Rules that apply to every file

### 0.1 Deleted flag (`cancellato`) is written nine ways
- **Where**: column `cancellato` in aziende, contatti, opportunita, listino, ticket, attivita.
- **How it's written**: `''`, `0`, `N`, `NO` mean not deleted; `1`, `S`, `s`, `SI`, `Sì` mean deleted.
- **How many**: companies 799 deleted of 20,497; contacts 2,802 of 73,391; deals ~1,443 of 35,020; price list 70 of 1,922; tickets 671 of 22,000; activities 10,713 of 370,316.
- **Rule**: deleted = trimmed, lower-cased value in {`1`, `s`, `si`, `sì`, `true`, `y`, `yes`}; anything else (including empty) is live. Deleted rows are not imported and never take part in duplicate detection. Status: decided.

### 0.2 References to rows that are not imported
- Deal `id_azienda` pointing to a deleted company (0 missing, some deleted), deal `contatti` pointing to missing contacts (737 refs), contact `id_azienda` missing (1,754) or deleted (1,881), ticket `id_contatto` missing (23) or deleted (691), ticket `id_azienda` deleted (596), activity `id_contatto` missing (3,665) or deleted (13,099), activity `id_opportunita` deleted (7,494), quote lines of deleted deals (1,722).
- **Rule**: such a reference is an empty field. The record is imported anyway, without that association. When duplicates are merged, an empty-by-reference field is empty, so the most recent row that holds a *valid* reference wins. A reference to a row merged into another goes to the surviving record. Status: decided.

### 0.3 Whitespace
- Names, titles, cities, emails, texts and codes carry leading/trailing spaces (companies 1,240 names, contacts 4,340 first names, tickets 1,189 subjects, activities 18,783 texts, quote codes, emails ` x@y.it  `).
- **Rule**: every string field is trimmed; internal whitespace and casing of names/texts are kept as written. Status: decided.

### 0.4 Duplicate merge
- When several live rows are the same record: the survivor keeps the `id_legacy` of the row with the latest `ultima_modifica`; each field takes the value of the most recent row that has a non-empty, valid value for it. `ultima_modifica` is always `dd/mm/yyyy HH:MM:SS` in every file. Status: decided.

### 0.5 Dates come in six shapes
- **Where**: `data_chiusura` (deals), `aperto_il`/`chiuso_il` (tickets), `data` (activities), `data_cambio` (history).
- **How it's written**: `18/01/2015`, `2018-05-17`, `16/03/2014 00:00:00`, `2024-08-17 12:14:15`, `17/08/2021 09:02`, `20-04-2017`, `19/9/2015`, `04.09.18` (dd.mm.yy, 2,239 deals), and Excel serial numbers `42466` (2,330 deals; 42466 = 2016-04-06, origin 1899-12-30).
- **Rule**: parse in this order: ISO `yyyy-mm-dd[ HH:MM[:SS]]`; `d/m/yyyy` and `d-m-yyyy` with optional time (day first: 6,592 rows have day > 12 in first position, none in second); `dd.mm.yy` with 2-digit year as 20yy; pure integer as Excel serial. All timestamps are taken as UTC and exposed as ISO 8601 (`2016-04-06T00:00:00Z`); date-only values are midnight UTC so year boundaries (R8) are unambiguous. Status: decided.

### 0.6 Money is written in twenty shapes
- **Where**: `importo` (deals), `prezzo_unitario` (quote lines), `prezzo_listino` (price list).
- **How it's written**: `116.903,80`, `205,657.60`, `2947.68`, `488210,35`, `1.247.204,29`, `1,257,280.17`, with currency `€`, `$`, `£`, `EUR`, `USD`, `GBP` before or after, with or without space.
- **Rule**: strip currency symbols/codes and spaces; if both `.` and `,` appear the last one is the decimal separator; if only one appears it is the decimal separator (in the export a lone separator is always followed by 1 or 2 digits, never 3, so no thousands ambiguity). Round to 2 decimals. Status: decided.

## 1. Companies (R1, R7)

### 1.1 Website to domain
- **Where**: `aziende.sito_web`. 3,216 empty.
- **How it's written**: `ferrarogroup.it`, `www.x.eu`, `http://www.x.it/`, `https://x.it`, `https://www.x.eu/chi-siamo`, `https://www.x.com/it/home`, 1,915 with upper-case letters.
- **Rule**: `domain` = lower-case host without scheme, `www.` and path. Status: decided.

### 1.2 The VAT number lives in the notes
- **Where**: `aziende.note` (free text), 10,799 rows carry one.
- **How it's written**: `partita iva 84874 281912`, `P. IVA: IT 40969350707`, `PI: 34340014470`, `P.IVA 67105837370`, `p.iva IT11476373136`, mixed with other notes separated by `,`, `;` or ` - `.
- **Rule**: regex `(?i)(p\.?\s*iva|partita\s*iva|\bpi)\s*[:\s]*(it\s*)?([\d\s]{11,})`, keep digits only; accept only exactly 11 digits. Stored in `partita_iva` (no `IT`, no spaces). Status: decided.

### 1.3 Duplicate companies: same domain or same VAT
- 1,154 domain groups (2,502 rows) and 1,275 VAT groups among live rows; 835 VAT groups span different domains (`nuovaalimentarirossi.com` vs `.it`, `x.it` vs `x-srl.it`), so VAT catches duplicates the domain misses, and vice versa.
- **Rule**: union-find over live rows linking by normalized domain and by VAT. Survivor per 0.4; `hs_additional_domains` = the other distinct domains of the group (`;`-separated); `partita_iva` = most recent non-empty VAT. Same name alone is not a duplicate (names like "Officine Cattaneo S.r.l." appear 16 times in different cities; only 2 name+city groups exist among rows with neither domain nor VAT). Status: decided.
- **What you ruled out**: merging by name+city (generator reuses names); treating the 681 domain groups with different cities as distinct (the request says same site = same company).

### 1.4 Fields
- `name` = trimmed `ragione_sociale`; `city` = trimmed `citta`; `state` = trimmed upper `provincia`; `domain` per 1.1; `website` = trimmed original URL (harmless extra); `id_legacy` = `id_azienda`.

## 2. Contacts (R2, R12)

### 2.1 Emails
- **Where**: `contatti.email`. Shapes: valid (`a.b@c.it`), upper-case (13,819, e.g. `ROBERTOPOZZI@X.IT`), padded with spaces (~6,700), placeholders `n.d.`, `da chiedere`, `-`, `nessuna`, `NO EMAIL` (~2,400), truncated `x@` (454) and `x@gmail` (487), obfuscated `x(at)gmail.com` (489) and `x @libero.it` (447), a phone number in the email field (35).
- **Rule**: trim, lower-case, replace `(at)` with `@`, remove spaces around `@`; then validate with `^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$`; anything that fails is an absent email. Status: decided (the `(at)` and ` @` repair is the one judgment call: those strings carry the complete address, the person just typed it oddly; truncated and placeholder values do not).

### 2.2 Duplicate contacts: same email
- 5,143 groups (11,301 rows) among live rows; within groups `tipo`, `telefono`, `id_azienda` often differ.
- **Rule**: union by normalized email; survivor per 0.4. Contacts without a valid email are never merged. Status: decided.

### 2.3 Fields
- `firstname`/`lastname` trimmed; `phone` trimmed, otherwise as written (`03/8764294`, `+39 354 827 5053`); `lifecyclestage`: `lead` → `lead`, `prospect` → `opportunity`, `cliente` → `customer`, `ex cliente`/`ex-cliente` → `other` (case and spaces ignored); `id_legacy` = `id_contatto`; association to the company from `id_azienda` (valid, live, mapped to the survivor).

### 2.4 R12 on migrated contacts
- 13,022 live contacts have no company; 12,487 of them have a valid email and 3,715 of those have a domain equal to a company's `domain` or one of its `hs_additional_domains`.
- **Rule**: after companies are merged, a contact that ends up without a company association (including those whose company reference was deleted/missing) and whose email domain matches a company gets associated to it. Never creates companies. Existing associations untouched. Free-mail domains (gmail.com, libero.it, ...) match only if a company really has that domain (none does in the sample). Status: decided.

## 3. Users (`utenti.csv`)
- 85 users, `attivo` in {`s`,`S`,`SI`,`n`,`N`,`NO`}; 20 inactive. `email` is the identifier used by `commerciale`, `assegnatario`, `autore`.
- **Rule**: active = trimmed lower value in {`s`,`si`,`sì`,`y`,`1`,`true`}. Deals and tickets followed by an inactive user get an empty `commerciale`/`assegnatario` (R3). Activities keep `autore` = the author's email even if inactive (R6 says who wrote it, nothing about leaving). Status: decided.

### 3.1 Sales rep written by name instead of id
- **Where**: `opportunita.id_commerciale`: 34,177 rows `Uxx`, 687 empty, 156 rows with a person's name in six shapes: `francesca marchetti`, `Pozzi Débora`, `Mazza E.`, `D'AMICO NICCOLÒ`, `N. Moretti`, `Mancini R.`.
- **Rule**: normalize (strip accents, lower, collapse spaces) and match against `nome cognome`, `cognome nome`, `n. cognome`, `cognome n.` built from `utenti.csv`. Six name pairs are ambiguous (Niccolò Bassi U22/U84, Marco Costa U29/U81, Luca Santoro U47/U83, Mattia Panzeri U65/U85, Serena Neri U72/U80, Sara Colombo U78/U82; each pair is one inactive plus one active user): resolve to the candidate that appears as `id_utente` in that deal's `storico_fasi` rows (the commercial always appears there: 34,177 of 34,177 `Uxx` deals), else to the active one. Unresolvable names → empty. Status: decided.

## 4. Deals (R3, R8)

### 4.1 Pipeline and stage spellings
- `pipeline`: `vendite `, `VENDITE`, `Vendite`, `rinnovi `, `Rinnovi`, `RINNOVI`, empty (1,072 → Vendite).
- `fase` (55 spellings): `06`, `06 VINTA`, `06 - Vinta`, `Vinta`, ` vinta`; renewals `R1`, `r1`, `R1 - Da rinnovare`, `Da rinnovare`, `DA RINNOVARE`, ..., `R4 - Non rinnovato`.
- **Rule**: lower, trim; if it starts with `01`..`07` or `r1`..`r4` use that code; else match the stage name (`contatto`, `qualifica`, `presentazione`, `decisione`, `contratto`, `vinta`, `persa`, `da rinnovare`, `in trattativa`, `rinnovato`, `non rinnovato`; test `non rinnovato` before `rinnovato`). Stage codes decide the pipeline when `pipeline` is empty (`r*` → Rinnovi). Map to `dealstage` per the appendix; Rinnovi stages get generated ids and are matched by label. Status: decided.

### 4.2 Amounts
- `importo` empty in 1,320 rows → no `amount`, no `deal_currency_code`.
- Currency: `valuta` in {`EUR`,`Euro`,`eur`,`€`,`USD`,`usd`,`$`,`GBP`,`gbp`,`£`, empty 8,445}; when empty, the symbol/code inside `importo` decides (`€`, `$`, `£`, `EUR`, `USD`, `GBP`); else `EUR`. No row has conflicting symbol and `valuta`.
- Negative amounts (831 rows): `€ -5.131,24`, `4,086.16-`, `- 21.527,35`, `-8571,64`; accounting parentheses `(20020,40)` (189 rows). All 1,020 credit-note deals ("Storno fattura ...", "Nota di credito n. ...", "NC 615/24 ...") are negative or parenthesized, all are in Vinta of Vendite, none has quote lines. **Rule**: a trailing `-`, a leading `-` (also after the currency) or parentheses make the amount negative; the amount stays negative in the CRM so R8 subtracts it. Status: decided.
- Multipliers: `k`/`K` (95 rows), `mila` (73), `mln`/`Mln`/`milione` (34): `€206,5k` = 206500, `6.5mila` = 6500, `152.5 mila` = 152500, `2 mln` = 2000000. **Rule**: multiply. Status: decided.
- Monthly amounts (841 rows, all in Rinnovi): `51.315,91 mensili`, `500,59 /mese`, `€ 1,641.59 al mese`. **Rule**: "I rinnovi sono annuali" → multiply by 12. Status: decided.
- Deals with quote lines (12,139 live): `amount` = sum of the line amounts (each rounded to the cent), overriding `importo`; 126 deals differ from `importo` by 1-2 cents, the rest match exactly, which confirms the per-line rounding. Currency stays the deal's (lines are in euro; all such deals are in EUR in the sample, assert it in the migration log). Status: decided.

### 4.3 Close date
- 1,356 live won and 1,574 live lost deals have no `data_chiusura`; every one of them has a `storico_fasi` row entering that closed stage. When both exist they agree on the day (2,060 of 2,060).
- **Rule**: `closedate` = parsed `data_chiusura`; if empty and the deal is closed (Vinta/Persa/Rinnovato/Non rinnovato), use the `data_cambio` of the latest history row whose `fase_nuova` maps to that stage. Open deals keep `data_chiusura` as the expected close date (13,088 rows). The history's last stage disagrees with `fase` in 3,396 deals (history is incomplete): `fase` wins, history is only used for the date. Status: decided.

### 4.4 Contacts of a deal
- `contatti`: `6582450`, `3615919,5256299`, `4675114;9275880`, `2096379 ; 9508018`, up to four ids. Some ids never exist (737, often 10-digit).
- **Rule**: split on `,` and `;`, trim, drop unknown/deleted, map merged contacts to survivors, associate each once (deal → contact type 3). Company: `id_azienda` → deal → company type 341 (primary 5). Status: decided.

### 4.5 Fields
- `dealname` trimmed `titolo`; `amount`; `deal_currency_code`; `pipeline`; `dealstage`; `closedate`; `commerciale` (section 3); `id_legacy` = `id_opportunita`. Computed: `hs_is_closed_won`, `hs_is_closed`, `hs_deal_stage_probability` from the stage.

## 5. Price list and quote lines (R4)

### 5.1 Product codes in six spellings
- `listino.codice_articolo`: `BF-62989`, `BF38295`, ` BF-89712`, `bf-98503`; always 5 digits.
- `righe_offerta.codice_articolo`: `BF-12288`, `art. 52614`, `BF 50096`, `bf49139`, `55091`, `BF.49711`; 1,173 rows have fewer than 5 digits (`BF 7096`, `01039`).
- **Rule**: `hs_sku` = `BF-` + digits zero-padded to 5. 889 line codes have no product in the price list (40,583 of 42,736 live lines match a live product): the line is imported with its own description and price, without product association. Status: decided.

### 5.2 Duplicate products
- 122 codes appear more than once (republished at a new price, sometimes with a longer description: `Dado autobloccante` → `Dado autobloccante M8`). 65 codes exist only as deleted rows; 5 codes whose latest row is deleted still have a live older row.
- **Rule**: among live rows of a code, the latest `ultima_modifica` gives `name` and `price`. One product per code. Status: decided.

### 5.3 Line fields
- `quantita`: `20`, `20,00`, `1 pz`, `197,2 m`, `141,3 kg`, `5 conf` → numeric part, decimal comma. `prezzo_unitario` empty in 2,761 rows, all with a known product → the product's price. `sconto`: empty → 0; `10%`, `25 %`, `15`, `15,0`, `0.2`, `0,25`, `0,03` → fractions below 1 with a decimal separator are ratios (`0,25` = 25%), everything else is already a percentage. `name` = trimmed `descrizione`, else the product's name. `amount` = round(quantity × price × (1 − discount/100), 2). Associations: line → deal (20/19), `hs_product_id` = product id (HubSpot has no line-item/product association type; we also store a line_items → products association readable through v4 for convenience). Status: decided.

## 6. Tickets (R5)

- `stato` (17 spellings) → stage: `nuovo`/`aperto` → Aperto; `in lavorazione`/`lavorazione` → In lavorazione; `in attesa`/`in attesa cliente`/`attesa cliente` → In attesa del cliente; `chiuso`/`risolto` → Chiuso. Status: decided.
- `priorita`: `bassa`/`1 - Bassa` → LOW; `media`/`2 - Media`/`Normale` → MEDIUM; `alta`/`3 - Alta` → HIGH; `urgente`/`4 - Urgente`/`URGENTE!!` → URGENT; empty (2,147) → no priority. Status: decided.
- `aperto_il` → `createdate`, `chiuso_il` → `closed_date` (every closed/resolved ticket has one, no open one does). `subject`/`content` trimmed, content kept whole. `assegnatario` per section 3. `id_legacy` = `id_ticket`.
- **The sender in the description**: 5,645 descriptions start with a line `Da: <email>`; 536 of those tickets have no `id_contatto`, and the email is a live contact's in 5,355 cases (agrees with `id_contatto` in 5,089 of 5,109 where both exist). **Rule**: when `id_contatto` is empty or invalid, the contact is the one whose email equals the `Da:` address, if any. Company only from `id_azienda`. Status: decided.

## 7. Activities (R6)

- `tipo` (16 spellings): `NOTA`/`Appunto`/`nota`/`Nota` → notes; `CHIAMATA`/`Telefonata`/`Tel.`/`Chiamata` → calls; `E-mail`/`email`/`Email`/`Mail` → emails; `Incontro`/`Meeting`/`Riunione`/`Visita` → meetings.
- `data` in three shapes (0.5) → `hs_timestamp`. Body → `hs_note_body` / `hs_call_body` / `hs_email_text` / `hs_meeting_body`, trimmed. `autore` = author's email (section 3). `id_legacy` = `id_attivita`. Associations to the contact (202/194/198/200) and the deal (214/206/210/212) when valid. 9,106 rows reference neither: imported without associations. Status: decided.

## 8. Revenue 2025 and class (R8)

- Won = `closedwon` in the default pipeline or `Rinnovato` in Rinnovi; `closedate` year 2025 (UTC); associated to the company. Credit notes are won deals with negative amounts in the same year, so plain summation already subtracts them. USD × 0.92, GBP × 1.17, EUR × 1. Sum, round to the cent, `fatturato_2025` as a number with two decimals (`0` when nothing); `classe_cliente` A ≥ 100000, B ≥ 20000, C > 0, empty otherwise. Computed once at the end of the migration. Status: decided.

## 9. Dormant customers (R9)

- Static list named `Clienti dormienti`, object type `0-2`. Members: companies with at least one won deal (any year, closedate not required) and no note/call/email/meeting dated in 2025 among the activities associated to its contacts or to its deals. Activities in 2026 do not rescue a company (the request says 2025). Computed at the end of the migration. Status: decided.

## 10. Behavior rules (R7, R10, R11, R12) on API writes

- R7: `partita_iva` normalized on write (strip, drop `IT`, drop spaces); a create with an existing value replies `409` and nothing is created. Unique partial index in PostgreSQL makes it safe under concurrency.
- R10: when a deal enters `closedwon` of pipeline `default` by create or update after the migration, create one ticket in pipeline `Assistenza`, stage `Aperto`, `subject` = `Avvio fornitura - <dealname>`, `assegnatario` = deal's `commerciale`, associated to the deal (28/27) and to the deal's companies (339/340). Once per deal, enforced by a primary key `(deal_id, rule)` in `automation_log`, so a deal moved back and forth never gets a second ticket. Migrated deals never fire it.
- R11: same trigger on `closedlost`: one task, `hs_task_subject` = `Richiamare: <dealname>`, `hs_timestamp` = entry time + 180 days, `hs_task_status` = `NOT_STARTED`, associated to the deal (216/215). Once per deal.
- R12: a contact created (API, batch, import, assistant) without a company association and with a valid email whose domain equals a company's `domain` or one of its `hs_additional_domains` is associated to that company (279/280, primary 1/2). Also when the email changes on a contact that has no company. Existing associations are never touched; no company is ever created.
- Automations run synchronously inside the write request (well within the 15 s the checks wait).

## Association type ids (HubSpot defined)

| From → to | typeId | inverse |
|---|---|---|
| contact → company | 279 (primary 1) | company → contact 280 (primary 2) |
| deal → contact | 3 | contact → deal 4 |
| deal → company | 341 (primary 5) | company → deal 342 (primary 6) |
| ticket → contact | 16 | contact → ticket 15 |
| ticket → company | 339 (primary 26) | company → ticket 340 (primary 25) |
| ticket → deal | 28 | deal → ticket 27 |
| deal → line item | 19 | line item → deal 20 |
| note → contact 202, company 190, deal 214, ticket 228 | | contact → note 201, company → note 189, deal → note 213, ticket → note 227 |
| call → contact 194, company 182, deal 206, ticket 220 | | contact → call 193, company → call 181, deal → call 205, ticket → call 219 |
| email → contact 198, company 186, deal 210, ticket 224 | | contact → email 197, company → email 185, deal → email 209, ticket → email 223 |
| meeting → contact 200, company 188, deal 212, ticket 226 | | contact → meeting 199, company → meeting 187, deal → meeting 211, ticket → meeting 225 |
| task → contact 204, company 192, deal 216, ticket 230 | | contact → task 203, company → task 191, deal → task 215, ticket → task 229 |
| quote → deal 64, line item 67, contact 69, company 71 | | deal → quote 63, line item → quote 68 |

## What is not done yet
- Filled in as the day goes (see section 3 of the choice sheet).
