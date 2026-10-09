# Choice sheet

Paste into the platform's Choices page between 15:00 and 15:30. Limit 20,000 characters.
Before pasting: confirm section 3 against the final gap list.

## 1. What you found in the data that the requests didn't say

**Case: the VAT number lives in the notes**

- **Where**: `aziende.csv`, column `note` (free text). No column holds a VAT number.
- **How it's written**: `pagamento 60gg DF FM, partita iva 84874 281912`; `P. IVA: IT 40969350707; cliente storico`.
- **How many rows**: 10,799 of 20,497 rows (10,399 live); 1,275 VAT numbers are shared by two to four live cards.
- **How you noticed**: R7 asks for `partita_iva` and no column has it; `note` shows the same five prefixes in half the rows.

**Case: duplicate companies linked by VAT but not by website**

- **Where**: `aziende.csv`, `sito_web` plus the VAT in `note`.
- **How it's written**: `nuovaalimentarirossi.com` and `www.nuovaalimentarirossi.it`, VAT `12976396502` on both; `officinemose.com` and `officinemose-srl.it`.
- **How many rows**: 1,154 groups share a website once normalized (2,502 cards); 1,275 share a VAT, 835 of them across different websites; 1,352 live cards have neither.
- **How you noticed**: R1 gives the website as "for example"; counting VAT collisions among cards with different websites showed a second, larger link.

**Case: sales reps written by name**

- **Where**: `opportunita.csv`, `id_commerciale`.
- **How it's written**: `francesca marchetti`, `Pozzi Débora`, `Mazza E.`, `D'AMICO NICCOLÒ`, `N. Moretti`, next to 34,177 `Uxx` values.
- **How many rows**: 156. Six names match two users each, one active and one who left (Niccolò Bassi is U22 and U84).
- **How you noticed**: 201 distinct values in a column for 85 users.

**Case: amounts, renewals, credit notes**

- **Where**: `opportunita.csv` `importo` and `valuta`; `righe_offerta.prezzo_unitario`.
- **How it's written**: `116.903,80`, `205,657.60`, `2947.68`, `1,257,280.17`, with `€`, `$`, `EUR`, `USD` before or after; `51.315,91 mensili`, `500,59 /mese`; `€206,5k`, `2 mln`; `Storno fattura 5079/2018` with `€ -5.131,24`; `Nota di credito n. 363/2016` with `4,086.16-`; `(20020,40)`.
- **How many rows**: `valuta` empty in 8,445 deals; 1,320 with no amount; 841 monthly, all in Rinnovi; 95 `k`, 73 `mila`, 34 `mln`; 1,020 credit-note titles (831 negative, 189 in parentheses), all in Vinta, none with quote lines.
- **How you noticed**: letters other than currency codes inside `importo`; R8 says to subtract what was reversed, and these rows are the only candidates.

**Case: dates and missing close dates**

- **Where**: `data_chiusura` (deals), `aperto_il` and `chiuso_il` (tickets), `data` (activities), `data_cambio` (`storico_fasi.csv`).
- **How it's written**: `18/01/2015`, `2018-05-17`, `17/08/2021 09:02`, `20-04-2017`, `19/9/2015`, `04.09.18`, `42466`; a deal in `06 VINTA` with empty `data_chiusura` whose `storico_fasi` row into `06` is dated `17/08/2021 09:02`.
- **How many rows**: `data_chiusura`: 10,866 `dd/mm/yyyy`, 3,464 ISO, 2,448 `dd-mm-yyyy`, 2,330 serials, 2,239 `dd.mm.yy`, 11,801 empty. Live closed deals without a date: 1,082 won and 1,574 lost, 2,656 in all, every one with a history row into that stage; where both exist they agree in 2,060 of 2,060 cases.
- **How you noticed**: `42466` as an Excel serial (origin 1899-12-30) is 2016-04-06, inside the neighbouring years; 6,592 rows have a day above 12 first, none second.

**Case: the ticket sender in the description**

- **Where**: `ticket.csv`, `descrizione` first line `Da: m.leone@cortimetalli.com`, next to `id_contatto`.
- **How many rows** (live): 5,471 descriptions start with `Da:`; 518 of those tickets have no `id_contatto`, 200 more point to a deleted or missing contact; the address matches a live contact in 5,199 tickets, 456 of them among those 718.
- **How you noticed**: empty `id_contatto` but a readable email on the first line.

**Case: emails and same-name contacts**

- **Where**: `contatti.csv`, `email`, with `nome`, `cognome`, `id_azienda`.
- **How it's written**: ` pagani.franco@outlook.it  `, `ROBERTOPOZZI@X.IT`, `alessia.vitale(at)gmail.com`, `beatrice.testa @libero.it`, `irene.bellini@`, `n.d.`, `NO EMAIL`, `+39 354 827 5053`; `Irene Bellini` twice at one company with `irene.bellini@` and `irene.bellini @libero.it`.
- **How many rows** (live): 13,300 upper-case, 6,523 padded, 1,401 empty; 2,381 placeholders in five shapes, 915 truncated, 489 `(at)`, 447 ` @`, each shape 441 to 500 rows; 125 phone numbers (66 like `+39 354 827 5053`, 59 like `03/8764294`); 5,143 groups (11,301 rows) share an address; 2,870 same-name groups inside one company, 714 with no valid email in any row.
- **How you noticed**: the invalid shapes form one flat band of 441 to 500 rows while padding and upper case appear thousands of times; after merging by email the same name still appeared twice under one company.

**Case: products, quantities, discounts**

- **Where**: `righe_offerta.csv` (`codice_articolo`, `quantita`, `sconto`, `prezzo_unitario`), `listino.csv`.
- **How it's written**: `BF-12288`, `art. 52614`, `BF 50096`, `bf49139`, `55091`, `BF.49711`, `BF 7096`; `20,00`, `1 pz`, `197,2 m`; `10%`, `25 %`, `15`, `0.2`, `0,25`.
- **How many rows** (live): 1,173 line codes with fewer than five digits; 2,080 of 41,014 lines (917 codes) have no live product; 2,640 without a price; 9,406 without a discount; 117 codes republished at a new price.
- **How you noticed**: joining by raw code matched a minority of lines.

**Case: encodings, deleted flags, whitespace**

- **Where**: `aziende.csv` (1,205 rows), `contatti.csv` (1,917), `ticket.csv` (1,537) mix UTF-8 rows into Windows-1252 files; `cancellato` in six files; every text column; `fase` (55 spellings).
- **How it's written**: company 312638 is the bytes `Societ\xc3\xa0 Verniciature` (UTF-8 for `Società`) where every other row writes `à` as the single byte `\xe0`; `cancellato` in {`''`, `0`, `N`, `NO`} and {`1`, `S`, `s`, `SI`, `Sì`}; `06`, `06 VINTA`, `06 - Vinta`, ` vinta`.
- **How many rows**: deleted: companies 799, contacts 2,802, deals 1,443, tickets 671, activities 10,713; 1,240 padded company names, 18,783 padded activity texts.
- **How you noticed**: decoding as Windows-1252 gave `SocietÃ ` plus a stray no-break space in 940 company names, 1,911 contact names, 998 ticket contents.

**Case: the small things the data settled**

- **Where**: `contatti.email`; `opportunita.contatti`, `pipeline`, `data_chiusura`; `utenti.attivo`; contacts without a company.
- **How it's written**: `gallo.enrico@fratellinegri89.it e enrico.gallo@hotmail.it` (also `/`, `;`, `,`); `contatti` = `3615919,5256299` with ids that exist nowhere; `attivo` in `s`, `S`, `SI`, `n`, `N`, `NO`.
- **How many rows**: 111 rows with two addresses; 737 contact ids in deals that never exist; 1,072 deals with empty pipeline; 13,088 open deals with a date; 85 users, 20 inactive; 2,955 surviving contacts with no company but a company's email domain, 971 only through `hs_additional_domains`.

## 2. How you handled it and why

**Case: the VAT number lives in the notes**

- **What your CRM does**: a case-insensitive pattern for the five prefixes, optional `IT`, then exactly eleven digits with spaces allowed between them; digits only go into `partita_iva`.
- **Why this reading**: R7 wants eleven digits without `IT` or spaces and the notes are the only source.
- **How you verified it**: 10,799 extractions, no `iva` mention left unmatched; unit tests on eight spellings; no two live companies share one.

**Case: duplicate companies linked by VAT but not by website**

- **What your CRM does**: union-find over live cards linking same normalized domain and same VAT; the survivor keeps the `id_legacy` of the latest `ultima_modifica`, each field takes the latest non-empty valid value, other domains go to `hs_additional_domains`.
- **Why this reading**: R1 gives the website as an example, not the only rule; a VAT identifies a legal entity more strongly, and 835 groups would stay split on the website alone.
- **What you ruled out**: name plus city: 912 live groups share both (`Officine Cattaneo S.r.l.` exists in 16 cities), only 2 among cards with neither website nor VAT.
- **How you verified it**: 2,312 rows merge into 2,060 groups, 17,386 companies survive, no two share a domain or VAT.

**Case: sales reps written by name**

- **What your CRM does**: normalize (accents, case, spaces) and match `nome cognome`, `cognome nome`, `n. cognome`, `cognome n.` from `utenti.csv`; an ambiguous name resolves to the user whose `id_utente` appears in that deal's `storico_fasi`, else the active one. An inactive rep leaves `commerciale` and `assegnatario` empty (R3, 8,218 deals).
- **Why this reading**: the rep is who moved the deal: in 34,177 of 34,177 `Uxx` deals that user appears in the history.
- **How you verified it**: unit tests on the six shapes and six ambiguous pairs; `commerciale` of every deal compared with the reference.

**Case: amounts, renewals, credit notes**

- **What your CRM does**: strip currency symbols; the last of `.` and `,` is the decimal separator, a lone one is the decimal separator; `k` and `mila` × 1,000, `mln` × 1,000,000; monthly amounts × 12; a leading or trailing `-` or parentheses make the amount negative and it stays so, which is how R8 subtracts it; currency from `valuta`, else the symbol, else `EUR`. A deal with quote lines is the sum of its lines, each rounded HALF_UP to the cent.
- **Why this reading**: a lone separator is always followed by one or two digits, never three; R3 says renewals are annual; credit notes are won deals in the same year, so a negative amount in the sum is exactly R8's rule.
- **How you verified it**: tests on 25 money strings; the HALF_UP sum reproduces `importo` to the cent in all 11,659 live deals with lines, half-even or float rounding misses over a thousand.

**Case: dates and missing close dates**

- **What your CRM does**: parse ISO, then `d/m/yyyy` and `d-m-yyyy` day first with optional time, then `dd.mm.yy` as 20yy, then a bare integer as an Excel serial; everything UTC, date-only values at midnight UTC so the R8 year boundary is unambiguous. An empty `closedate` on a closed deal is the `data_cambio` of the latest history row into that stage; where the history disagrees with `fase` (3,396 deals), `fase` wins.
- **What you ruled out**: month first; trusting the history over `fase`.
- **How you verified it**: tests on the nine shapes (`42466` becomes `2016-04-06T00:00:00Z`); 2,656 close dates come from the history.

**Case: the ticket sender in the description**

- **What your CRM does**: when `id_contatto` is empty or points to a deleted or missing contact, the contact is the live contact whose email (or additional email) equals the `Da:` address; the company only from `id_azienda`.
- **Why this reading**: the header agrees with a valid `id_contatto` in all but 20 of the rows holding both.
- **What you ruled out**: overriding a valid `id_contatto` (those 20 are the operator's choice).
- **How you verified it**: 456 tickets get their contact this way; the first version missed the deleted-contact ones and the reference comparison caught it.

**Case: emails and same-name contacts**

- **What your CRM does**: trim and lower-case; `(at)`, a space before `@`, truncated addresses and placeholders are absent emails, not repaired. A phone number in the email field moves to `phone`. Contacts merge by any shared address; then, inside one company, same first and last name joins the same person unless that would join two different valid emails.
- **Why this reading**: R2 says an invalid email is absent. `(at)` and ` @` occur as often as `n.d.` or `NO EMAIL`, one family of placeholders, and none of the 936 rows has a twin holding the repaired address. The same-name rule recovers the 714 groups email cannot.
- **What you ruled out**: repairing `(at)` and ` @`; merging by name across companies (7,055 of 7,218 names appear at several companies).
- **How you verified it**: tests on twelve shapes; 63,710 contacts survive from 6,879 merged rows, 721 merges by name; no two share an email.

**Case: products, quantities, discounts**

- **What your CRM does**: `hs_sku` = `BF-` plus digits zero-padded to five; one product per code, `name` and `price` from the latest live row; a line with no live product keeps its own description and price; `quantity` is the numeric part; an empty price takes the product's; a discount below 1 with a decimal separator is a ratio (`0,25` is 25%), everything else is a percentage, empty is 0.
- **Why this reading**: the price list always has five digits, so `7096` is `07096`; `0,25` sits next to `25 %`.
- **How you verified it**: 1,735 products, 41,014 line items, 2,640 prices from the product; line totals reproduce `importo`.

**Case: encodings, deleted flags, whitespace**

- **What your CRM does**: decode each field as Windows-1252; if the result re-encodes to bytes that are valid UTF-8 with non-ASCII characters, take the UTF-8 decoding; repair before trimming. Deleted = trimmed lower value in {`1`, `s`, `si`, `sì`, `true`, `y`, `yes`}; deleted rows are not imported and never count as duplicates; a reference to a deleted or missing row is empty, to a merged row goes to the survivor. Every string is trimmed; stages, status, priority and activity types map by code or label.
- **What you ruled out**: decoding whole files as UTF-8 (the other 95% of rows break).
- **How you verified it**: unit tests on a mixed fixture; every `id_legacy` is present once, deleted or merged; counts per type match the reference.

**Case: the small things the data settled**

- **What your CRM does**: the first valid address is `email`, the others `hs_additional_emails`; unknown contact ids are dropped and the deal imported anyway; an empty pipeline is Vendite unless the stage code is `r1`..`r4` (0 rows); open deals keep `data_chiusura` as the expected close date; inactive users' deals and tickets get an empty `commerciale` or `assegnatario`, activity authors are kept; after companies merge, R12 runs on migrated contacts, free-mail domains never match.
- **How you verified it**: all in the reference comparison.

**R8, R9 and the behavior rules**

- **What your CRM does**: `fatturato_2025` sums won deals with `closedate` in 2025 UTC, USD × 0.92, GBP × 1.17, HALF_UP to the cent; credit notes subtract through their negative amounts. `Clienti dormienti` is a static list computed at the end of the migration. R7 is a unique partial index in PostgreSQL, so a duplicate `partita_iva` gets `409` even under concurrent creates. R10 and R11 fire once per deal through a primary key on (deal, rule); migrated deals never fire. R12 runs on create and on email change.
- **How you verified it**: an independent implementation of all the rules (`tests/reference/sinergia.py`, 6 seconds on the export) agrees with the CRM on every `fatturato_2025` and `classe_cliente` (52 A, 25 B, 65 C) and on the whole dormant list (936 companies); acceptance tests for R7, R10, R11, R12 and concurrent writes.

## 3. What you didn't do

- **Requests left out or half done**: (to be confirmed at 14:15)
- **Cases seen and not handled**:
  - The 20 tickets where the `Da:` header and a valid `id_contatto` disagree keep `id_contatto`.
  - The 936 `(at)` and ` @` emails stay absent.
  - The 3,396 deals whose stage history disagrees with `fase` keep `fase`.
- **What you would do with one more hour**: (to be confirmed at 14:15)

## 4. The assistant

- **What it can do**: answer questions on companies, contacts, deals, tickets, products and activities, also by Sinergia code; 2025 revenue and class through the same R8 computation as the migration; deal counts and totals by stage, rep, pipeline or year; a rep's own customers (deals they follow or tickets assigned to them); the dormant list. It creates and updates contacts, companies, deals, tickets, notes, calls, emails, meetings and tasks; associates, dissociates and archives records; previews and imports an attached Sinergia CSV of any of the seven kinds.
- **How it works**: `openai/gpt-6-luna` through OpenRouter with native tool calling and 24 typed tools, 17 reads and 7 writes. Every tool runs against the same store as the API, so an assistant write passes the same validation and fires R7, R10, R11 and R12 like an API call. The system prompt carries `context.now` as today, the writer's user card from `utenti.csv` and the pipeline and stage ids; the whole conversation is replayed every turn. Names match in either word order ignoring `srl` or `spa`; `commerciale` and `assegnatario` are accepted by name. An attached CSV is read with the migration's own normalisers: the header decides the kind, Sinergia references (company, contact, deal, article, user) resolve to CRM records, rows already present by email, VAT, article code or Sinergia id are never duplicated, a preview tool answers questions on the attachment without writing, and the import goes row by row through the same validation, updating existing rows only on explicit request (price list excepted, R4).
- **When it asks, when it says no**: a write needs exactly one target. When a search returns several plausible candidates (the same name in two cities, several open deals of one company) it lists them with city, amount or stage and asks which, without asking for what the request already says. A request against the rules is not carried out and the reply says why: a VAT already in use (the store answers `409`), a company to be created from an email domain, a deal or ticket for a colleague who left (refused before the write, R3), deleting history without a stated reason. A question the data cannot answer gets "non lo so" rather than a guess.
- **How you avoid damage**: write tools take record ids, never names, so every write follows a search the model has read; each write runs in its own transaction and a failed one is rolled back and removed from the list of things done, so the reply cannot claim it; there is no bulk update or delete tool; multi-record creation is capped at 200 rows per call. Assistant Insights is an optional panel under each reply (switch "Show evidence"): it shows the CRM operations the backend actually ran for that reply, each tool call in order with its outcome, writes split into requested, returned and commit confirmed, the record ids read or written with links and the associations the results carried, the revenue sum with its inputs, and a list of limits (empty searches, rejected writes, partial traces). It never shows raw arguments or results. It proves what the CRM did; it does not show the model's reasoning or prompts.

## Where to look

- **The CRM**: https://faithful-emotion-production-1fe1.up.railway.app
- **A company page, the deals board, the dormant customers, the tickets**: `/companies` and `/companies/{id}`, `/deals` (board; dragging a deal fires R10 and R11), `/dormant`, `/tickets`, `/assistant` (also a side panel on every screen). Sign in with the CRM token.
- **The repo**: https://github.com/Canonik/brambilla-crm (public): `DECISIONS.md`, the reference implementation in `tests/reference/sinergia.py`, the assistant in `server/app/assistant/`, the acceptance suite in `tests/acceptance/`.
