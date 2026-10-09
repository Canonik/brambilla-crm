# Choice sheet draft (paste into the platform between 15:00 and 15:30, max 20,000 chars)

Update the numbers in section 3 and the URLs at the end before pasting. Keep it checkable:
file, column, example row, row count, what the CRM does.

## 1. What you found in the data that the requests didn't say

**Case: VAT numbers hidden in the notes**
- Where: `aziende.csv`, column `note` (free text).
- How it's written: `pagamento 60gg DF FM, partita iva 84874 281912`; `P. IVA: IT 40969350707; cliente storico`; `PI: 34340014470`; `referente amm.ne sig.ra Colombo, p.iva IT11476373136`.
- How many rows: 10,799 of 20,497 companies carry one; 1,275 VAT numbers are shared by two or three live cards.
- How you noticed: R7 asks for `partita_iva` but no column holds it; profiling `note` showed the same five prefixes everywhere.

**Case: duplicate companies linked by VAT but not by website**
- Where: `aziende.csv`, `sito_web` and the VAT in `note`.
- How it's written: `nuovaalimentarirossi.com` vs `www.nuovaalimentarirossi.it` with VAT 12976396502 on both; `officinemose.com` vs `officinemose-srl.it` with VAT 34340014470.
- How many rows: 1,154 groups share a website (2,502 cards); 835 VAT groups span different websites; 1,352 live cards have neither.
- How you noticed: R1 says "for example, two cards with the same website"; counting VAT collisions among cards with different websites showed a second, larger link.

**Case: sales reps written by name instead of user id**
- Where: `opportunita.csv`, column `id_commerciale`.
- How it's written: `francesca marchetti`, `Pozzi Débora`, `Mazza E.`, `D'AMICO NICCOLÒ`, `N. Moretti`, `Mancini R.` next to 34,177 `Uxx` values and 687 empties.
- How many rows: 156. Six names match two users each (one active, one who left): Niccolò Bassi, Marco Costa, Luca Santoro, Mattia Panzeri, Serena Neri, Sara Colombo.
- How you noticed: 201 distinct values for 85 users.

**Case: monthly amounts in annual renewals**
- Where: `opportunita.csv`, column `importo`, pipeline Rinnovi only.
- How it's written: `51.315,91 mensili`, `500,59 /mese`, `€ 1,641.59 al mese`.
- How many rows: 841, all in Rinnovi.
- How you noticed: letters other than currency codes inside `importo`; R3 says "I rinnovi sono annuali".

**Case: credit notes as won deals with negative amounts**
- Where: `opportunita.csv`, `titolo` and `importo`.
- How it's written: `Storno fattura 5079/2018 - Officine Sironi` with `€ -5.131,24`; `Nota di credito n. 363/2016 - Fratelli Marino` with `4,086.16-`; `(20020,40)` in accounting parentheses.
- How many rows: 1,020 credit-note titles: 831 negative, 189 in parentheses, all in Vinta, none with quote lines.
- How you noticed: R8 says to subtract what was "stornato"; the only candidates are these.

**Case: amounts with thousand/million suffixes**
- Where: `opportunita.csv`, `importo`: `€206,5k`, `6.5mila`, `152.5 mila`, `€8mila`, `2 mln`.
- How many rows: 95 `k`, 73 `mila`, 34 `mln`/`milione`.

**Case: close dates as Excel serial numbers and dd.mm.yy**
- Where: `opportunita.csv`, `data_chiusura`: `42466`, `04.09.18`, `20-04-2017`, `19/9/2015`, `16/03/2014 00:00:00`.
- How many rows: 2,330 serials, 2,239 dd.mm.yy, 1,872 with a time, 5,912 ISO, 10,866 dd/mm/yyyy.

**Case: closed deals without a close date**
- Where: `opportunita.csv` `data_chiusura` empty while `fase` is Vinta/Persa/Rinnovato/Non rinnovato; `storico_fasi.csv` has the entry into that stage.
- How many rows: 1,356 won and 1,574 lost live deals; every one has the history row; where both exist they agree on the day in 2,060 of 2,060 cases.

**Case: the ticket sender in the description**
- Where: `ticket.csv`, `descrizione` first line `Da: m.leone@cortimetalli.com`.
- How many rows: 5,645; 536 of them have no `id_contatto`; the email matches a live contact in 5,355 cases and agrees with `id_contatto` in 5,089 of 5,109 where both exist.

**Case: emails typed oddly**
- Where: `contatti.csv`, `email`: ` pagani.franco@outlook.it  `, `ROBERTOPOZZI@X.IT`, `alessia.vitale(at)gmail.com`, `beatrice.testa @libero.it`, `irene.bellini@`, `noemi.cattaneo@gmail`, `n.d.`, `da chiedere`, `NO EMAIL`, a phone number.
- How many rows: 6,700 padded, 13,819 upper-case, 489 `(at)`, 447 ` @`, 941 truncated, 2,400 placeholders, 35 phones; 5,143 duplicate groups by email after normalization.

**Case: product codes in six spellings, quantities with units, discounts as ratios**
- Where: `righe_offerta.csv` (`BF-12288`, `art. 52614`, `BF 50096`, `bf49139`, `55091`, `BF.49711`; `1 pz`, `197,2 m`; `0,25`, `25 %`, `0.03`), `listino.csv` (`BF38295`, ` BF-89712`, `bf-98503`; 122 codes republished at a new price).
- How many rows: 1,173 line codes with fewer than 5 digits; 889 line codes with no product; 2,761 lines without a price; 9,804 without a discount.

**Case: UTF-8 rows inside Windows-1252 files**
- Where: `aziende.csv` (1,205 rows), `contatti.csv` (1,917), `ticket.csv` (1,537); the other six files are pure cp1252.
- How it's written: company 312638 is the bytes `Societ\xc3\xa0 Verniciature` in a file where the other rows write `à` as one byte.
- How you noticed: decoding everything as cp1252 produced `SocietÃ ` in 940 company names, 326 cities, 1,911 contact names, 998 ticket contents and 368 subjects; the migration and the independent oracle disagreed on exactly those rows until the per-field repair was added.

**Case: the deleted flag written nine ways; whitespace everywhere**
- `cancellato` in {`''`,`0`,`N`,`NO`,`1`,`S`,`s`,`SI`,`Sì`}; 1,240 company names, 4,340 first names, 1,189 ticket subjects, 18,783 activity texts padded with spaces.

## 2. How you handled it and why

(One block per case above; the rule in one sentence, why, what was ruled out, how verified.
Source: `DECISIONS.md` sections 0 to 9 of the repo. Summaries:)

- VAT: regex on the five prefixes, keep exactly 11 digits, stored without `IT`/spaces; verified by counting 10,799 extractions and zero unmatched "iva" mentions.
- Duplicate companies: union of same website and same VAT; survivor is the latest modified card, each field from the latest card that has it, other websites into `hs_additional_domains`. Ruled out name+city (names repeat across cities; only 2 such groups exist). Verified: no two surviving companies share a domain or VAT.
- Reps by name: normalized name match against `utenti.csv` in four shapes; ambiguous pairs resolved by the user who moved that deal in `storico_fasi` (the official rep always appears there: 34,177 of 34,177), else the active one. Inactive reps leave `commerciale`/`assegnatario` empty (R3); activity authors are kept (R6 asks who wrote it).
- Monthly amounts × 12; `k`/`mila` × 1,000; `mln` × 1,000,000; parentheses and leading/trailing minus negative; amounts stay negative so R8 subtracts them.
- Deals with quote lines take the sum of their lines, each line rounded to the cent (12,013 of 12,139 match `importo` exactly, the other 126 differ by 1-2 cents, which is the rounding the request describes).
- Close dates: six formats parsed day-first; missing close date on a closed deal taken from the history entry into that stage. `fase` wins over the history's last stage where they disagree (3,396 deals).
- Tickets: `Da:` email resolves the contact when `id_contatto` is empty or points to a deleted/missing contact (456 tickets).
- Encodings: each field decoded as cp1252, re-read as UTF-8 when the bytes are valid UTF-8 with non-ASCII characters, before trimming.
- Emails: trimmed, lower-cased, `(at)` and ` @` repaired, then validated; the rest is an absent email; duplicates merged by email.
- Products: `BF-` + five zero-padded digits; latest live row per code; lines without a product keep their own description and price.
- R8/R9 computed at the end of the migration from the imported records (fixed FX 0.92 / 1.17, class thresholds, dormant = at least one won deal and no 2025 activity among the company's contacts' and deals' activities).

## 3. What you didn't do

- Requests left out or half done: (fill in at 15:00)
- Cases seen and not handled: (fill in)
- With one more hour: (fill in, in order)

## 4. The assistant

- What it can do: read companies, contacts, deals, tickets, revenue and class; create and update contacts, companies, deals (stage, amount, close date), tickets, notes and tasks; import contacts from an attached CSV; answer "my customers" questions from `commerciale`/`assegnatario`.
- How it works: `openai/gpt-6-luna` with native tool calling; every tool is a validated function over the same service layer as the API, so R7, R10, R11, R12 fire exactly as for API calls; up to 8 tool rounds per turn; the whole conversation is replayed each turn as the contract says; `context.now` is the clock.
- When it asks, when it says no: a write needs exactly one matching record, otherwise it asks; a request that breaks a rule (duplicate VAT, moving a migrated deal's history, creating companies from an email domain) is refused with the reason; questions it cannot answer from the CRM are answered with "non lo so".
- How you avoid damage: ids resolved by search before any write, the tool arguments are the ids, never names; writes are logged as a trace shown in the interface's execution inspector; no delete tool.

## Where to look

- The CRM: https://<railway-domain>
- Company page `/companies/<id>`, deals board `/deals`, dormant customers `/dormant`, tickets `/tickets`, assistant `/assistant`. Sign in with the CRM token (or the jury password given on the platform).
- The repo: https://github.com/Canonik/brambilla-crm
