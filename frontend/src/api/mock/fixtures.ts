// Deterministic demo data shaped like Brambilla's migrated CRM. Only used when
// VITE_USE_MOCKS=true; production talks to the real API.

import { USERS } from "../users";
import type { Pipeline } from "../types";

export type Row = { id: string; properties: Record<string, string>; createdAt: string; updatedAt: string };

export interface MockDb {
  companies: Row[];
  contacts: Row[];
  deals: Row[];
  tickets: Row[];
  products: Row[];
  line_items: Row[];
  notes: Row[];
  calls: Row[];
  emails: Row[];
  meetings: Row[];
  tasks: Row[];
  // associations[fromType][fromId][toType] = Set<toId>
  assoc: Record<string, Record<string, Record<string, Set<string>>>>;
  pipelines: { deals: Pipeline[]; tickets: Pipeline[] };
  dormantIds: string[];
  nextId: number;
}

function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const rnd = mulberry32(20261202);
const pick = <T,>(arr: readonly T[]): T => arr[Math.floor(rnd() * arr.length)]!;
const chance = (p: number) => rnd() < p;
const between = (lo: number, hi: number) => lo + rnd() * (hi - lo);
const intBetween = (lo: number, hi: number) => Math.floor(between(lo, hi + 1));

const NOW = Date.now();

function isoDate(year: number, month?: number, day?: number, hour?: number) {
  const m = month ?? intBetween(1, 12);
  const d = day ?? intBetween(1, 28);
  const h = hour ?? intBetween(8, 18);
  return new Date(Date.UTC(year, m - 1, d, h, intBetween(0, 59))).toISOString();
}

/** A timestamp that is never in the future (for created/updated fields). */
function pastIso(fromYear: number) {
  const t = Date.parse(isoDate(fromYear));
  return new Date(t > NOW ? NOW - intBetween(1, 120) * 86400000 - intBetween(0, 86399) * 1000 : t).toISOString();
}

const COMPANY_NAMES = [
  "Nuova Impianti Benedetti S.p.A.",
  "Ferraro Group S.r.l.s.",
  "Trasporti Perego S.r.l.",
  "Officine Sironi S.r.l.",
  "Lamiere Pagani S.p.A.",
  "Alimentari De Luca S.r.l.",
  "Fratelli Rota S.n.c.",
  "Zanè Pneumatica S.r.l.",
  "Nuova Serramenti Mazza",
  "Nuova Tessile Spinelli S.p.A.",
  "Società Arredi Palumbo",
  "Corti Metalli S.r.l.",
  "Greco & Oggionni S.r.l.",
  "Ruggeri Minuterie S.a.s.",
  "Basile Logistica S.r.l.",
  "Bellini & Lo Russo S.p.A.",
  "Ferraro Logistica Pavia",
  "Officine Viganò S.r.l.",
  "Nuova Automazione Oggionni",
  "Fratelli Dalò S.r.l.",
  "Valsecchi Martinelli S.p.A.",
  "Carpenteria Brianza S.r.l.",
  "Elettroforniture Lario",
  "Tornerie Riunite Varesine",
  "Plastica Ticino S.p.A.",
  "Colombo Verniciature S.r.l.",
  "Meccanica Precisa Seregno",
  "Galvanica Lecchese S.r.l.",
  "Stampaggio Adda S.p.A.",
  "Idraulica Fumagalli S.n.c.",
  "Arredo Ufficio Monza S.r.l.",
  "Cantiere Navale Sestri",
  "Marmi e Graniti Verona",
  "Autotrasporti Bergamaschi",
  "Cartotecnica Emiliana S.r.l.",
  "Caseificio Padano S.p.A.",
  "Impianti Elettrici Riva",
  "Edilizia Comasca S.r.l.",
  "Fonderia Lodigiana S.p.A.",
  "Tessitura Castellanza S.r.l.",
  "Vetreria Bresciana S.p.A.",
  "Molino Reggiano S.r.l.",
  "Ascensori Padovani S.r.l.",
  "Imballaggi Mantovani S.n.c.",
  "Chimica Lombarda S.p.A.",
  "Officina Meccanica Sala",
  "Serramenti Alluminio Nord",
  "Gomma Tecnica Varese S.r.l.",
];

const CITIES: Array<[string, string]> = [
  ["Varese", "VA"],
  ["Milano", "MI"],
  ["Como", "CO"],
  ["Monza", "MB"],
  ["Lecco", "LC"],
  ["Padova", "PD"],
  ["Bologna", "BO"],
  ["Lodi", "LO"],
  ["Reggio Emilia", "RE"],
  ["Verona", "VR"],
  ["Genova", "GE"],
  ["Busto Arsizio", "VA"],
  ["Seregno", "MB"],
  ["Treviso", "TV"],
  ["Pavia", "PV"],
  ["Bergamo", "BG"],
];

const FIRST = ["Elisa", "Roberto", "Marta", "Giorgia", "Valentina", "Luca", "Andrea", "Paolo", "Chiara", "Matteo", "Sara", "Davide", "Federica", "Simone", "Laura", "Alessandro", "Francesca", "Stefano", "Giulia", "Marco"];
const LAST = ["Bellini", "Pozzi", "Sartori", "Colombo", "Leone", "Ferrari", "Russo", "Galli", "Fontana", "Moretti", "Brambilla", "Villa", "Riva", "Cattaneo", "Sala", "Mariani", "Crippa", "Fumagalli", "Longoni", "Arrigoni"];
const TITLES = ["Purchasing manager", "Plant manager", "Owner", "Administration", "Warehouse lead", "Maintenance manager", "Buyer", "CEO", "Operations"];

const SECTORS = ["verniciature", "torneria", "minuterie", "lamiere", "elettroforniture", "logistica", "carpenteria", "guanti e DPI", "fissaggi", "utensili"];

const PRODUCTS = [
  ["BF-62989", "Guanti in nitrile taglia L", 112.98],
  ["BF-38295", "Dado autobloccante M8", 158.14],
  ["BF-73083", "Guanti antitaglio taglia 8", 191.52],
  ["BF-19798", "Schiuma poliuretanica 750 ml", 268.73],
  ["BF-89712", "Nastro americano 50 mm x 25 m", 513.52],
  ["BF-76380", "Cuscinetto a sfere 6205 2RS", 47.51],
  ["BF-95927", "Tubo in polietilene Ø 25", 18.75],
  ["BF-70113", "Nastro americano 50 mm x 50 m", 158.49],
  ["BF-77655", "Vite TE zincata M10", 2.4],
  ["BF-83587", "Valvola a sfera ottone 1/2", 1223.4],
  ["BF-60614", "Silicone acetico trasparente", 5.13],
  ["BF-12288", "Pallet in legno EPAL 1200x800", 15.17],
  ["BF-35446", "Disco da taglio inox 125 mm", 1151.12],
  ["BF-10860", "Occhiali protettivi antiappannamento", 72.54],
  ["BF-44120", "Scarpe antinfortunistiche S3 n. 42", 89.9],
  ["BF-51777", "Grasso al litio 5 kg", 64.2],
  ["BF-20931", "Catena zincata 6 mm (metro)", 3.85],
  ["BF-66104", "Cassetta pronto soccorso gruppo A", 149.0],
] as const;

const TICKET_SUBJECTS = [
  "Problema con l'ordine",
  "Danni durante il trasporto",
  "Merce mancante",
  "Fattura non corretta",
  "Richiesta nota di credito",
  "Ritardo consegna",
  "Dichiarazione di conformità",
  "Ricambio difettoso",
  "Reso materiale",
  "Richiesta listino aggiornato",
];
const TICKET_BODIES = [
  "Il DDT non riporta il numero d'ordine.",
  "Il cliente segnala che la merce è arrivata danneggiata.",
  "Manca un collo su tre.",
  "Il prezzo in fattura è più alto di quello concordato.",
  "Chiede l'emissione di una nota di credito.",
  "Chiede la consegna entro venerdì.",
  "Serve la dichiarazione di conformità per il collaudo.",
  "Spedito il ricambio con corriere espresso.",
  "Già sollecitato il magazzino, in attesa di risposta.",
  "Cliente richiamato, problema risolto.",
];

const NOTE_BODIES = [
  "Promemoria su campionatura guanti: inviare taglie M e L.",
  "Inviato listino 2025 IVA esclusa.",
  "Chiede sconto 3% su ordini sopra 5.000 euro.",
  "Referente amministrazione: sig.ra Colombo, pagamento 60gg DF FM.",
  "Visita in sede fissata per la settimana prossima.",
  "Da richiamare dopo le ferie, interessato ai DPI.",
  "Confermato ordine quadro per il 2026.",
  "Preventivo inviato, attende approvazione dalla direzione.",
];
const CALL_BODIES = [
  "Chiamato per sollecitare offerta, richiamare giovedì.",
  "Telefonata con il responsabile acquisti: conferma quantità.",
  "Non risponde, lasciato messaggio in segreteria.",
  "Discusso tempi di consegna, ok per fine mese.",
];
const EMAIL_BODIES = [
  "Buongiorno, in allegato l'offerta aggiornata come concordato.",
  "Vi confermiamo la disponibilità a magazzino degli articoli richiesti.",
  "Gentile cliente, la spedizione partirà domani con corriere espresso.",
  "Come anticipato, le condizioni di pagamento restano 60 giorni.",
];
const MEETING_BODIES = [
  "Incontro in sede per presentazione nuova gamma DPI.",
  "Riunione con ufficio acquisti: definito piano consegne.",
  "Sopralluogo in stabilimento per fornitura verniciature.",
  "Incontrato il titolare per preventivo ordine quadro.",
];

const SALES_STAGES = [
  ["appointmentscheduled", "Appointment scheduled", "0.2"],
  ["qualifiedtobuy", "Qualified to buy", "0.4"],
  ["presentationscheduled", "Presentation scheduled", "0.6"],
  ["decisionmakerboughtin", "Decision maker bought-in", "0.8"],
  ["contractsent", "Contract sent", "0.9"],
  ["closedwon", "Closed won", "1.0"],
  ["closedlost", "Closed lost", "0.0"],
] as const;

const RENEWAL_STAGES = [
  ["1001", "Da rinnovare", "0.2"],
  ["1002", "In trattativa", "0.6"],
  ["1003", "Rinnovato", "1.0"],
  ["1004", "Non rinnovato", "0.0"],
] as const;

const SUPPORT_STAGES = [
  ["2001", "Aperto", "OPEN"],
  ["2002", "In lavorazione", "OPEN"],
  ["2003", "In attesa del cliente", "OPEN"],
  ["2004", "Chiuso", "CLOSED"],
] as const;

const FX: Record<string, number> = { EUR: 1, USD: 0.92, GBP: 1.17 };

export function buildMockDb(): MockDb {
  const db: MockDb = {
    companies: [],
    contacts: [],
    deals: [],
    tickets: [],
    products: [],
    line_items: [],
    notes: [],
    calls: [],
    emails: [],
    meetings: [],
    tasks: [],
    assoc: {},
    pipelines: {
      deals: [
        {
          id: "default",
          label: "Sales Pipeline",
          displayOrder: 0,
          stages: SALES_STAGES.map(([id, label, probability], i) => ({
            id,
            label,
            displayOrder: i,
            metadata: { isClosed: String(id.startsWith("closed")), probability },
          })),
        },
        {
          id: "renewals",
          label: "Rinnovi",
          displayOrder: 1,
          stages: RENEWAL_STAGES.map(([id, label, probability], i) => ({
            id,
            label,
            displayOrder: i,
            metadata: { isClosed: String(i >= 2), probability },
          })),
        },
      ],
      tickets: [
        {
          id: "support",
          label: "Assistenza",
          displayOrder: 0,
          stages: SUPPORT_STAGES.map(([id, label, state], i) => ({
            id,
            label,
            displayOrder: i,
            metadata: { isClosed: String(state === "CLOSED"), ticketState: state },
          })),
        },
      ],
    },
    dormantIds: [],
    nextId: 100001,
  };

  const newId = () => String(db.nextId++);
  const link = (fromType: string, fromId: string, toType: string, toId: string) => {
    const a = (db.assoc[fromType] ??= {});
    const b = (a[fromId] ??= {});
    (b[toType] ??= new Set()).add(toId);
  };
  const both = (t1: string, i1: string, t2: string, i2: string) => {
    link(t1, i1, t2, i2);
    link(t2, i2, t1, i1);
  };
  const row = (properties: Record<string, string>, created: string, updated?: string): Row => ({
    id: newId(),
    properties,
    createdAt: created,
    updatedAt: updated ?? created,
  });

  const activeUsers = USERS.map((u) => u.email);

  // Products
  for (const [sku, name, price] of PRODUCTS) {
    db.products.push(row({ name, hs_sku: sku, price: price.toFixed(2), description: name }, isoDate(2012)));
  }

  // Companies
  for (const name of COMPANY_NAMES) {
    const [city, state] = pick(CITIES);
    const domain = name
      .toLowerCase()
      .replace(/s\.?p\.?a\.?|s\.?r\.?l\.?s?\.?|s\.?n\.?c\.?|s\.?a\.?s\.?/g, "")
      .replace(/&/g, "e")
      .replace(/[^a-z0-9]+/g, "")
      .slice(0, 24);
    const created = isoDate(intBetween(2011, 2023));
    const props: Record<string, string> = {
      name,
      domain: `${domain}.it`,
      city,
      state,
      partita_iva: String(intBetween(10000000000, 99999999999)),
      id_legacy: String(intBetween(100000, 999999)),
      createdate: created,
      hs_lastmodifieddate: pastIso(intBetween(2022, 2026)),
      fatturato_2025: "0",
      classe_cliente: "",
    };
    if (chance(0.2)) props.hs_additional_domains = `${domain}.com`;
    if (chance(0.6)) props.phone = `0${intBetween(2, 39)} ${intBetween(100000, 999999)}`;
    if (chance(0.5)) props.description = pick(["cliente storico", "pagamento 60gg DF FM", "sconto 3% su ordini > 5.000", "referente amm.ne sig.ra Colombo"]);
    db.companies.push(row(props, created));
  }

  // Contacts
  for (const company of db.companies) {
    const n = intBetween(1, 4);
    for (let i = 0; i < n; i++) {
      const first = pick(FIRST);
      const last = pick(LAST);
      const created = isoDate(intBetween(2011, 2025));
      const props: Record<string, string> = {
        firstname: first,
        lastname: last,
        email: `${first[0]!.toLowerCase()}.${last.toLowerCase()}@${company.properties.domain}`,
        lifecyclestage: pick(["customer", "customer", "customer", "opportunity", "lead", "other"]),
        jobtitle: pick(TITLES),
        company: company.properties.name!,
        associatedcompanyid: company.id,
        id_legacy: String(intBetween(1000000, 9999999)),
        createdate: created,
        lastmodifieddate: pastIso(intBetween(2021, 2026)),
      };
      if (chance(0.7)) props.phone = `3${intBetween(20, 99)} ${intBetween(1000000, 9999999)}`;
      const c = row(props, created);
      db.contacts.push(c);
      both("companies", company.id, "contacts", c.id);
    }
  }
  // A few contacts without a company (R12 candidates).
  for (let i = 0; i < 6; i++) {
    const first = pick(FIRST);
    const last = pick(LAST);
    const created = pastIso(2025);
    const c = row(
      {
        firstname: first,
        lastname: last,
        email: `${first.toLowerCase()}.${last.toLowerCase()}@${pick(["libero.it", "gmail.com", "pec.it"])}`,
        lifecyclestage: "lead",
        id_legacy: String(intBetween(1000000, 9999999)),
        createdate: created,
        lastmodifieddate: created,
      },
      created,
    );
    db.contacts.push(c);
  }

  // Deals
  const contactsOf = (companyId: string) => Array.from(db.assoc.companies?.[companyId]?.contacts ?? []);
  for (const company of db.companies) {
    const n = intBetween(1, 6);
    for (let i = 0; i < n; i++) {
      const renewal = chance(0.25);
      const pipeline = renewal ? "renewals" : "default";
      const stages = renewal ? RENEWAL_STAGES : SALES_STAGES;
      const weights = renewal ? [2, 2, 5, 2] : [2, 2, 2, 2, 2, 7, 4];
      let r = rnd() * weights.reduce((a, b) => a + b, 0);
      let idx = 0;
      while (r > weights[idx]!) {
        r -= weights[idx]!;
        idx++;
      }
      const [stageId] = stages[idx]!;
      const closed = renewal ? idx >= 2 : stageId.startsWith("closed");
      const year = closed ? pick([2019, 2021, 2023, 2024, 2025, 2025, 2025, 2026]) : 2026;
      const shortName = company.properties.name!.replace(/ S\.?p\.?A\.?| S\.?r\.?l\.?s?\.?| S\.?n\.?c\.?| S\.?a\.?s\.?/g, "");
      const title = renewal
        ? pick([`Rinnovo contratto ${shortName} ${year}`, `${shortName} - ordine quadro`])
        : pick([`Fornitura ${pick(SECTORS)} ${shortName}`, `Offerta ${intBetween(9000, 9999)}/${shortName}`, `${shortName} - ordine quadro`]);
      const currency = pick(["EUR", "EUR", "EUR", "EUR", "EUR", "USD", "GBP"]);
      const amount = chance(0.08) ? null : Math.round(between(800, 180000) * 100) / 100;
      const created = isoDate(Math.max(2011, year - intBetween(0, 1)));
      const closedate = closed ? isoDate(year) : isoDate(2026, intBetween(10, 12));
      const props: Record<string, string> = {
        dealname: title,
        pipeline,
        dealstage: stageId,
        closedate,
        commerciale: pick(activeUsers),
        id_legacy: String(intBetween(10000000, 99999999)),
        createdate: created,
        hs_lastmodifieddate: pastIso(intBetween(2024, 2026)),
      };
      if (amount !== null) {
        props.amount = amount.toFixed(2);
        props.deal_currency_code = currency;
      }
      const d = row(props, created, props.hs_lastmodifieddate);
      db.deals.push(d);
      both("deals", d.id, "companies", company.id);
      const cs = contactsOf(company.id);
      for (const cid of cs.slice(0, intBetween(0, 2))) both("deals", d.id, "contacts", cid);

      // Line items
      if (chance(0.45) && amount !== null) {
        const k = intBetween(1, 4);
        let total = 0;
        const items: Row[] = [];
        for (let j = 0; j < k; j++) {
          const p = pick(db.products);
          const quantity = intBetween(1, 40);
          const price = Number(p.properties.price);
          const discount = pick([0, 0, 5, 10, 15]);
          const lineTotal = Math.round(quantity * price * (1 - discount / 100) * 100) / 100;
          total += lineTotal;
          items.push(
            row(
              {
                name: p.properties.name!,
                quantity: String(quantity),
                price: price.toFixed(2),
                hs_discount_percentage: String(discount),
                amount: lineTotal.toFixed(2),
                hs_sku: p.properties.hs_sku!,
                hs_product_id: p.id,
                id_legacy: String(intBetween(1000000000, 9999999999)),
              },
              created,
            ),
          );
        }
        d.properties.amount = total.toFixed(2);
        d.properties.deal_currency_code = "EUR";
        for (const li of items) {
          db.line_items.push(li);
          both("deals", d.id, "line_items", li.id);
          both("line_items", li.id, "products", li.properties.hs_product_id!);
        }
      }

      // R11: lost deals got a callback task.
      if (stageId === "closedlost" && chance(0.5)) {
        const due = new Date(Date.parse(closedate) + 180 * 86400000).toISOString();
        const t = row(
          {
            hs_task_subject: `Richiamare: ${title}`,
            hs_task_status: chance(0.3) ? "COMPLETED" : "NOT_STARTED",
            hs_timestamp: due,
            autore: props.commerciale!,
          },
          closedate,
        );
        db.tasks.push(t);
        both("tasks", t.id, "deals", d.id);
      }
    }
  }

  // Tickets
  const supportIds = SUPPORT_STAGES.map(([id]) => id);
  for (let i = 0; i < 72; i++) {
    const company = pick(db.companies);
    const cs = contactsOf(company.id);
    const stageIdx = pick([0, 0, 1, 1, 2, 3, 3, 3, 3]);
    const stage = supportIds[stageIdx]!;
    const year = stageIdx === 3 ? pick([2021, 2023, 2024, 2025, 2026]) : 2026;
    const created = year === 2026 ? pastIso(2026) : isoDate(year);
    const subjectBase = pick(TICKET_SUBJECTS);
    const subject = chance(0.4) ? `${subjectBase} - ordine ${intBetween(40000, 49999)}` : subjectBase;
    const props: Record<string, string> = {
      subject,
      content: pick(TICKET_BODIES),
      hs_pipeline: "support",
      hs_pipeline_stage: stage,
      createdate: created,
      assegnatario: pick(activeUsers),
      id_legacy: String(intBetween(100000, 999999)),
      hs_lastmodifieddate: created,
    };
    const priority = pick(["LOW", "MEDIUM", "MEDIUM", "HIGH", "URGENT", ""]);
    if (priority) props.hs_ticket_priority = priority;
    if (stageIdx === 3) props.closed_date = new Date(Date.parse(created) + intBetween(1, 20) * 86400000).toISOString();
    const t = row(props, created);
    db.tickets.push(t);
    both("tickets", t.id, "companies", company.id);
    if (cs.length) both("tickets", t.id, "contacts", pick(cs));
  }
  // R10: a couple of "Avvio fornitura" tickets on won deals.
  for (const d of db.deals.filter((x) => x.properties.dealstage === "closedwon").slice(0, 5)) {
    const companyId = Array.from(db.assoc.deals?.[d.id]?.companies ?? [])[0];
    const t = row(
      {
        subject: `Avvio fornitura - ${d.properties.dealname}`,
        content: "Ticket aperto automaticamente alla vincita della trattativa.",
        hs_pipeline: "support",
        hs_pipeline_stage: "2001",
        createdate: d.properties.closedate!,
        assegnatario: d.properties.commerciale!,
        hs_lastmodifieddate: d.properties.closedate!,
      },
      d.properties.closedate!,
    );
    db.tickets.push(t);
    both("tickets", t.id, "deals", d.id);
    if (companyId) both("tickets", t.id, "companies", companyId);
  }

  // Activities: notes, calls, emails, meetings on contacts and deals.
  const activityYears = [2014, 2016, 2018, 2020, 2022, 2023, 2024, 2025, 2025, 2026];
  const quietCompanies = new Set(db.companies.filter(() => chance(0.3)).map((c) => c.id));
  for (const contact of db.contacts) {
    const companyId = contact.properties.associatedcompanyid;
    const quiet = companyId ? quietCompanies.has(companyId) : false;
    const n = intBetween(0, 6);
    for (let i = 0; i < n; i++) {
      let year = pick(activityYears);
      if (quiet && year >= 2025) year = 2024;
      const ts = isoDate(year);
      const kind = pick(["notes", "notes", "calls", "emails", "meetings"] as const);
      const autore = pick(activeUsers);
      const body =
        kind === "notes" ? pick(NOTE_BODIES) : kind === "calls" ? pick(CALL_BODIES) : kind === "emails" ? pick(EMAIL_BODIES) : pick(MEETING_BODIES);
      const props: Record<string, string> = { hs_timestamp: ts, autore, id_legacy: String(intBetween(100000000, 999999999)) };
      if (kind === "notes") props.hs_note_body = body;
      if (kind === "calls") {
        props.hs_call_body = body;
        props.hs_call_title = "Chiamata";
      }
      if (kind === "emails") {
        props.hs_email_text = body;
        props.hs_email_subject = pick(["Offerta aggiornata", "Conferma disponibilità", "Spedizione", "Condizioni di pagamento"]);
      }
      if (kind === "meetings") {
        props.hs_meeting_body = body;
        props.hs_meeting_title = pick(["Incontro in sede", "Riunione acquisti", "Sopralluogo", "Presentazione gamma"]);
      }
      const a = row(props, ts);
      db[kind].push(a);
      both(kind, a.id, "contacts", contact.id);
      if (companyId && chance(0.4)) {
        const deals = Array.from(db.assoc.companies?.[companyId]?.deals ?? []);
        if (deals.length) both(kind, a.id, "deals", pick(deals));
      }
    }
  }

  // R8: revenue 2025 and class.
  for (const company of db.companies) {
    const dealIds = Array.from(db.assoc.companies?.[company.id]?.deals ?? []);
    let total = 0;
    for (const id of dealIds) {
      const d = db.deals.find((x) => x.id === id)!;
      const won = d.properties.dealstage === "closedwon" || d.properties.dealstage === "1003";
      if (!won) continue;
      if (!d.properties.closedate?.startsWith("2025")) continue;
      const amount = Number(d.properties.amount ?? "0");
      const fx = FX[d.properties.deal_currency_code ?? "EUR"] ?? 1;
      total += amount * fx;
    }
    total = Math.round(total * 100) / 100;
    company.properties.fatturato_2025 = total.toFixed(2);
    company.properties.classe_cliente = total >= 100000 ? "A" : total >= 20000 ? "B" : total > 0 ? "C" : "";
  }

  // R9: dormant customers = at least one won deal ever, no activity in 2025.
  const activityKinds = ["notes", "calls", "emails", "meetings"] as const;
  for (const company of db.companies) {
    const dealIds = Array.from(db.assoc.companies?.[company.id]?.deals ?? []);
    const hasWon = dealIds.some((id) => {
      const d = db.deals.find((x) => x.id === id)!;
      return d.properties.dealstage === "closedwon" || d.properties.dealstage === "1003";
    });
    if (!hasWon) continue;
    const contactIds = contactsOf(company.id);
    let active2025 = false;
    for (const kind of activityKinds) {
      for (const a of db[kind]) {
        if (!a.properties.hs_timestamp?.startsWith("2025")) continue;
        const cs = db.assoc[kind]?.[a.id]?.contacts ?? new Set();
        const ds = db.assoc[kind]?.[a.id]?.deals ?? new Set();
        if (contactIds.some((c) => cs.has(c)) || dealIds.some((d) => ds.has(d))) {
          active2025 = true;
          break;
        }
      }
      if (active2025) break;
    }
    if (!active2025) db.dormantIds.push(company.id);
  }

  return db;
}
