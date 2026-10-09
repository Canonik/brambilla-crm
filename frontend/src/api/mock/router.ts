// A small in-browser imitation of the HubSpot-compatible API, enough to drive
// every screen in development without a backend. Enabled only with
// VITE_USE_MOCKS=true.

import type { RequestOptions } from "../client";
import { ApiError } from "../client";
import type { AgentRequest, Filter, SearchRequest } from "../types";
import { buildMockDb, type MockDb, type Row } from "./fixtures";
import { USERS } from "../users";

let db: MockDb | null = null;
function getDb() {
  if (!db) db = buildMockDb();
  return db;
}

const SEARCHABLE = ["name", "domain", "firstname", "lastname", "email", "dealname", "subject", "content", "hs_sku", "city"];

type Collection = keyof Pick<
  MockDb,
  "companies" | "contacts" | "deals" | "tickets" | "products" | "line_items" | "notes" | "calls" | "emails" | "meetings" | "tasks"
>;

const COLLECTIONS: Collection[] = ["companies", "contacts", "deals", "tickets", "products", "line_items", "notes", "calls", "emails", "meetings", "tasks"];

const SINGULAR: Record<string, Collection> = {
  company: "companies",
  contact: "contacts",
  deal: "deals",
  ticket: "tickets",
  product: "products",
  line_item: "line_items",
  note: "notes",
  call: "calls",
  email: "emails",
  meeting: "meetings",
  task: "tasks",
};

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

function project(row: Row, properties: string[] | undefined, extra: Record<string, unknown> = {}) {
  const props: Record<string, string | null> = { hs_object_id: row.id };
  const wanted = properties && properties.length ? properties : Object.keys(row.properties);
  for (const key of wanted) props[key] = row.properties[key] ?? null;
  return { id: row.id, properties: props, createdAt: row.createdAt, updatedAt: row.updatedAt, archived: false, ...extra };
}

function withAssociations(d: MockDb, type: Collection, row: Row, assocTypes: string[] | undefined) {
  if (!assocTypes?.length) return undefined;
  const out: Record<string, { results: Array<{ id: string; type: string }> }> = {};
  for (const to of assocTypes) {
    const ids = Array.from(d.assoc[type]?.[row.id]?.[to] ?? []);
    out[to] = { results: ids.map((id) => ({ id, type: `${type.slice(0, -1)}_to_${to.slice(0, -1)}` })) };
  }
  return out;
}

function compare(a: string | undefined, b: string | undefined) {
  const na = Number(a);
  const nb = Number(b);
  if (a !== undefined && b !== undefined && a !== "" && b !== "" && Number.isFinite(na) && Number.isFinite(nb)) return na - nb;
  const da = Date.parse(a ?? "");
  const dbb = Date.parse(b ?? "");
  if (Number.isFinite(da) && Number.isFinite(dbb)) return da - dbb;
  return (a ?? "").localeCompare(b ?? "", "en", { sensitivity: "base" });
}

function matchFilter(d: MockDb, type: Collection, row: Row, f: Filter): boolean {
  if (f.propertyName.startsWith("associations.")) {
    const toSingular = f.propertyName.slice("associations.".length);
    const to = SINGULAR[toSingular] ?? (toSingular as Collection);
    const ids = d.assoc[type]?.[row.id]?.[to] ?? new Set<string>();
    const values = f.values ?? (f.value !== undefined ? [f.value] : []);
    return values.some((v) => ids.has(String(v)));
  }
  const v = row.properties[f.propertyName];
  switch (f.operator) {
    case "EQ":
      return (v ?? "") === String(f.value ?? "");
    case "NEQ":
      return (v ?? "") !== String(f.value ?? "");
    case "IN":
      return (f.values ?? []).map(String).includes(v ?? "");
    case "NOT_IN":
      return !(f.values ?? []).map(String).includes(v ?? "");
    case "HAS_PROPERTY":
      return v !== undefined && v !== "";
    case "NOT_HAS_PROPERTY":
      return v === undefined || v === "";
    case "GT":
      return v !== undefined && compare(v, String(f.value)) > 0;
    case "GTE":
      return v !== undefined && compare(v, String(f.value)) >= 0;
    case "LT":
      return v !== undefined && compare(v, String(f.value)) < 0;
    case "LTE":
      return v !== undefined && compare(v, String(f.value)) <= 0;
    case "BETWEEN":
      return v !== undefined && compare(v, String(f.value)) >= 0 && compare(v, String(f.highValue)) <= 0;
    case "CONTAINS_TOKEN":
      return (v ?? "").toLowerCase().includes(String(f.value ?? "").toLowerCase());
    case "NOT_CONTAINS_TOKEN":
      return !(v ?? "").toLowerCase().includes(String(f.value ?? "").toLowerCase());
    default:
      return true;
  }
}

function search(d: MockDb, type: Collection, body: SearchRequest) {
  let rows = d[type].slice();
  if (body.filterGroups?.length) {
    rows = rows.filter((row) => body.filterGroups!.some((g) => g.filters.every((f) => matchFilter(d, type, row, f))));
  }
  if (body.query?.trim()) {
    const q = body.query.trim().toLowerCase();
    rows = rows.filter((row) => SEARCHABLE.some((k) => (row.properties[k] ?? "").toLowerCase().includes(q)));
  }
  for (const s of (body.sorts ?? []).slice().reverse()) {
    const dir = s.direction === "DESCENDING" ? -1 : 1;
    rows.sort((a, b) => dir * compare(a.properties[s.propertyName], b.properties[s.propertyName]));
  }
  const limit = Math.min(Math.max(Number(body.limit ?? 10), 0), 200);
  const offset = Number(body.after ?? 0) || 0;
  const page = rows.slice(offset, offset + limit);
  const next = offset + limit < rows.length ? String(offset + limit) : undefined;
  return {
    total: rows.length,
    results: page.map((r) => project(r, body.properties)),
    ...(next ? { paging: { next: { after: next } } } : {}),
  };
}

function parseQuery(path: string) {
  const [pathname, qs = ""] = path.split("?");
  const params = new URLSearchParams(qs);
  return { pathname: pathname!, params };
}

function listParam(params: URLSearchParams, key: string) {
  const v = params.get(key);
  return v ? v.split(",").filter(Boolean) : undefined;
}

function agentReply(body: AgentRequest, d: MockDb): string {
  const last = body.messages.filter((m) => m.role === "user").at(-1)?.content ?? "";
  const q = last.toLowerCase();
  const company = d.companies.find((c) => q.includes(c.properties.name!.split(" ").slice(0, 2).join(" ").toLowerCase()));
  if (q.includes("fatturat") && company) {
    const v = Number(company.properties.fatturato_2025 ?? 0);
    return `Nel 2025 con **${company.properties.name}** abbiamo fatturato **€ ${v.toLocaleString("it-IT", { minimumFractionDigits: 2 })}** (classe ${company.properties.classe_cliente || "non assegnata"}).`;
  }
  if (q.includes("vinta") && company) {
    const dealId = Array.from(d.assoc.companies?.[company.id]?.deals ?? []).find((id) => {
      const deal = d.deals.find((x) => x.id === id)!;
      return deal.properties.pipeline === "default" && !deal.properties.dealstage!.startsWith("closed");
    });
    if (!dealId) return `Non trovo trattative aperte per ${company.properties.name}. Vuoi che ne crei una?`;
    const deal = d.deals.find((x) => x.id === dealId)!;
    deal.properties.dealstage = "closedwon";
    deal.properties.hs_lastmodifieddate = body.context.now;
    const ticket: Row = {
      id: String(d.nextId++),
      properties: {
        subject: `Avvio fornitura - ${deal.properties.dealname}`,
        content: "Ticket aperto automaticamente alla vincita della trattativa.",
        hs_pipeline: "support",
        hs_pipeline_stage: "2001",
        createdate: body.context.now,
        assegnatario: deal.properties.commerciale!,
        hs_lastmodifieddate: body.context.now,
      },
      createdAt: body.context.now,
      updatedAt: body.context.now,
    };
    d.tickets.push(ticket);
    ((d.assoc.tickets ??= {})[ticket.id] ??= {}).deals = new Set([deal.id]);
    ((d.assoc.tickets[ticket.id] ??= {}).companies = new Set([company.id]));
    ((d.assoc.deals[deal.id] ??= {}).tickets ??= new Set()).add(ticket.id);
    return `Fatto: ho segnato come **vinta** la trattativa "${deal.properties.dealname}" di ${company.properties.name}.\n\nIl CRM ha aperto il ticket **Avvio fornitura - ${deal.properties.dealname}** nella pipeline Assistenza, assegnato a ${deal.properties.commerciale}.`;
  }
  if (q.includes("miei clienti") || q.includes("i miei")) {
    const mine = d.deals.filter((x) => x.properties.commerciale === body.context.user).slice(0, 5);
    if (!mine.length) return "Non risultano trattative seguite da te al momento.";
    return `Ecco le tue trattative più recenti:\n\n${mine.map((x) => `- **${x.properties.dealname}** (${x.properties.amount ? `€ ${Number(x.properties.amount).toLocaleString("it-IT")}` : "importo non indicato"})`).join("\n")}`;
  }
  if (q.includes("dormient")) {
    return `I clienti dormienti al momento sono **${d.dormantIds.length}**. Li trovi nella lista "Clienti dormienti" del CRM.`;
  }
  return "Posso aiutarti a cercare aziende, contatti e trattative, aggiornare una trattativa o aprire un ticket. Dimmi il nome dell'azienda o della trattativa e cosa vuoi fare.";
}

function agentEvidence(body: AgentRequest, d: MockDb) {
  const last = body.messages.filter((message) => message.role === "user").at(-1)?.content ?? "";
  const q = last.toLowerCase();
  const company = d.companies.find((item) => q.includes(item.properties.name!.split(" ").slice(0, 2).join(" ").toLowerCase()));
  if (q.includes("fatturat") && company) {
    const dealIds = Array.from(d.assoc.companies?.[company.id]?.deals ?? []);
    const rates: Record<string, number> = { EUR: 1, USD: 0.92, GBP: 1.17 };
    const matchingDeals = dealIds.map((id) => d.deals.find((deal) => deal.id === id)).filter((deal): deal is Row => Boolean(deal))
      .filter((deal) => deal.properties.dealstage === "closedwon" && (deal.properties.closedate ?? "").startsWith("2025"));
    const deals = matchingDeals.slice(0, 20);
    const terms = deals.map((deal) => ({
      record: { type: "deals", id: deal.id },
      amount: (Number(deal.properties.amount ?? 0) * (rates[deal.properties.deal_currency_code ?? "EUR"] ?? 1)).toFixed(2),
    }));
    const result = terms.reduce((sum, term) => sum + Number(term.amount), 0).toFixed(2);
    return {
      version: 1, incomplete: matchingDeals.length > 20,
      events: [
        { sequence: 1, call: 1, tool: "search_companies", operation: "read", status: "attempted" },
        { sequence: 2, call: 1, tool: "search_companies", operation: "read", status: "completed", durationMs: 18, inputSummary: "Company lookup", records: [{ type: "companies", id: company.id }] },
        { sequence: 3, call: 2, tool: "revenue", operation: "read", status: "attempted" },
        { sequence: 4, call: 2, tool: "revenue", operation: "read", status: "completed", durationMs: 27, inputSummary: `Revenue for company #${company.id} in 2025`, records: [{ type: "companies", id: company.id }, ...terms.map((term) => term.record)], calculation: { kind: "sum_money_v1", policy: "brambilla_revenue_v1", currency: "EUR", populationComplete: matchingDeals.length <= 20, populationCount: matchingDeals.length, terms, result, year: 2025 } },
      ],
    };
  }
  return {
    version: 1, incomplete: false,
    events: [
      { sequence: 1, call: 1, tool: "search_companies", operation: "read", status: "attempted" },
      { sequence: 2, call: 1, tool: "search_companies", operation: "read", status: "completed", durationMs: 18, inputSummary: "Company lookup", records: d.companies.slice(0, 2).map((item) => ({ type: "companies", id: item.id })) },
    ],
  };
}

export async function mockRequest<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const d = getDb();
  const method = opts.method ?? "GET";
  const { pathname, params } = parseQuery(path);
  const query = { ...Object.fromEntries(params.entries()), ...(opts.query ?? {}) } as Record<string, unknown>;
  const qlist = (key: string): string[] | undefined => {
    const v = query[key];
    if (Array.isArray(v)) return v.map(String);
    if (typeof v === "string") return v.split(",").filter(Boolean);
    return listParam(params, key);
  };
  await sleep(120 + Math.random() * 220);

  if (pathname === "/health") {
    return {
      status: "ok",
      version: "2026-09",
      ui: { companies: "/companies", contacts: "/contacts", deals: "/deals", tickets: "/tickets", dormant: "/dormant", assistant: "/assistant" },
    } as T;
  }

  if (pathname === "/crm/v3/owners") {
    return {
      results: USERS.map((u, i) => ({
        id: `U${String(i + 1).padStart(2, "0")}`,
        email: u.email,
        firstName: u.name.split(" ")[0],
        lastName: u.name.split(" ").slice(1).join(" "),
        role: u.role,
        archived: false,
        active: true,
      })),
    } as T;
  }

  if (pathname === "/__agente" && method === "POST") {
    await sleep(600 + Math.random() * 900);
    const body = opts.body as AgentRequest;
    const response: Record<string, unknown> = { reply: agentReply(body, d) };
    if (String(query.trace ?? "") === "1") {
      response.trace = agentEvidence(body, d);
    }
    return response as T;
  }

  let m: RegExpMatchArray | null;

  if ((m = pathname.match(/^\/crm\/v3\/pipelines\/(deals|tickets)$/))) {
    return { results: d.pipelines[m[1] as "deals" | "tickets"] } as T;
  }

  if ((m = pathname.match(/^\/crm\/v3\/lists\/object-type-id\/([^/]+)\/name\/(.+)$/))) {
    const name = decodeURIComponent(m[2]!);
    if (m[1] === "0-2" && name === "Clienti dormienti") {
      return { list: { listId: "dormant-1", name, objectTypeId: "0-2", processingType: "SNAPSHOT" } } as T;
    }
    throw new ApiError("List not found", 404);
  }

  if ((m = pathname.match(/^\/crm\/v3\/lists\/([^/]+)\/memberships$/))) {
    const limit = Number(query.limit ?? 100);
    const offset = Number(query.after ?? 0) || 0;
    const ids = d.dormantIds;
    const page = ids.slice(offset, offset + limit);
    const next = offset + limit < ids.length ? String(offset + limit) : undefined;
    return {
      results: page.map((recordId) => ({ recordId, membershipTimestamp: "2026-12-01T22:00:00Z" })),
      total: ids.length,
      ...(next ? { paging: { next: { after: next } } } : {}),
    } as T;
  }

  if ((m = pathname.match(/^\/crm\/v4\/objects\/([a-z_]+)\/([^/]+)\/associations\/([a-z_]+)$/))) {
    const [, type, id, to] = m;
    const ids = Array.from(d.assoc[type as Collection]?.[id!]?.[to as Collection] ?? []);
    return { results: ids.map((toObjectId) => ({ toObjectId, associationTypes: [] })) } as T;
  }

  if ((m = pathname.match(/^\/crm\/v3\/objects\/([a-z_]+)\/search$/)) && method === "POST") {
    const type = m[1] as Collection;
    if (!COLLECTIONS.includes(type)) throw new ApiError("Unknown object type", 404);
    return search(d, type, (opts.body ?? {}) as SearchRequest) as T;
  }

  if ((m = pathname.match(/^\/crm\/v3\/objects\/([a-z_]+)\/batch\/read$/)) && method === "POST") {
    const type = m[1] as Collection;
    const body = opts.body as { inputs: Array<{ id: string }>; properties?: string[] };
    const wanted = new Set(body.inputs.map((i) => String(i.id)));
    const results = d[type].filter((r) => wanted.has(r.id)).map((r) => project(r, body.properties));
    return { status: "COMPLETE", results } as T;
  }

  if ((m = pathname.match(/^\/crm\/v3\/objects\/([a-z_]+)\/([^/]+)$/))) {
    const type = m[1] as Collection;
    const id = decodeURIComponent(m[2]!);
    if (!COLLECTIONS.includes(type)) throw new ApiError("Unknown object type", 404);
    const row = d[type].find((r) => r.id === id);
    if (!row) throw new ApiError(`${type.slice(0, -1)} ${id} not found`, 404, { category: "OBJECT_NOT_FOUND" });
    if (method === "PATCH") {
      const body = opts.body as { properties: Record<string, string> };
      if (type === "companies" && body.properties.partita_iva) {
        const clash = d.companies.find((c) => c.id !== id && c.properties.partita_iva === body.properties.partita_iva);
        if (clash) throw new ApiError("A company with this VAT number already exists", 409, { category: "CONFLICT" });
      }
      const wasStage = row.properties.dealstage;
      Object.assign(row.properties, body.properties);
      const now = new Date().toISOString();
      row.updatedAt = now;
      if (type === "deals") row.properties.hs_lastmodifieddate = now;
      if (type === "tickets") row.properties.hs_lastmodifieddate = now;
      if (type === "deals" && body.properties.dealstage === "closedwon" && wasStage !== "closedwon" && row.properties.pipeline === "default") {
        const already = Array.from(d.assoc.deals?.[row.id]?.tickets ?? []).some((tid) =>
          d.tickets.find((t) => t.id === tid)?.properties.subject?.startsWith("Avvio fornitura - "),
        );
        if (!already) {
          const ticket: Row = {
            id: String(d.nextId++),
            properties: {
              subject: `Avvio fornitura - ${row.properties.dealname}`,
              content: "Ticket aperto automaticamente alla vincita della trattativa.",
              hs_pipeline: "support",
              hs_pipeline_stage: "2001",
              createdate: now,
              assegnatario: row.properties.commerciale ?? "",
              hs_lastmodifieddate: now,
            },
            createdAt: now,
            updatedAt: now,
          };
          d.tickets.push(ticket);
          const companies = d.assoc.deals?.[row.id]?.companies ?? new Set<string>();
          ((d.assoc.tickets ??= {})[ticket.id] ??= {}).deals = new Set([row.id]);
          d.assoc.tickets[ticket.id]!.companies = new Set(companies);
          ((d.assoc.deals[row.id] ??= {}).tickets ??= new Set()).add(ticket.id);
          for (const cid of companies) ((d.assoc.companies[cid] ??= {}).tickets ??= new Set()).add(ticket.id);
        }
      }
      return project(row, undefined) as T;
    }
    const assoc = withAssociations(d, type, row, qlist("associations"));
    return project(row, qlist("properties"), assoc ? { associations: assoc } : {}) as unknown as T;
  }

  if ((m = pathname.match(/^\/crm\/v3\/objects\/([a-z_]+)$/))) {
    const type = m[1] as Collection;
    if (!COLLECTIONS.includes(type)) throw new ApiError("Unknown object type", 404);
    if (method === "POST") {
      const body = opts.body as {
        properties: Record<string, string>;
        associations?: Array<{ to: { id: string }; types: Array<{ associationTypeId: number }> }>;
      };
      const now = new Date().toISOString();
      const row: Row = { id: String(d.nextId++), properties: { ...body.properties }, createdAt: now, updatedAt: now };
      d[type].push(row);
      for (const a of body.associations ?? []) {
        const to = COLLECTIONS.find((c) => d[c].some((r) => r.id === String(a.to.id)));
        if (!to) continue;
        ((d.assoc[type] ??= {})[row.id] ??= {})[to] = new Set([...(d.assoc[type]![row.id]![to] ?? []), String(a.to.id)]);
        ((d.assoc[to] ??= {})[String(a.to.id)] ??= {})[type] = new Set([...(d.assoc[to]![String(a.to.id)]![type] ?? []), row.id]);
      }
      return project(row, undefined) as T;
    }
    const limit = Number(query.limit ?? 10);
    const offset = Number(query.after ?? 0) || 0;
    const rows = d[type];
    const page = rows.slice(offset, offset + limit);
    const next = offset + limit < rows.length ? String(offset + limit) : undefined;
    return {
      results: page.map((r) => project(r, qlist("properties"))),
      ...(next ? { paging: { next: { after: next } } } : {}),
    } as T;
  }

  throw new ApiError(`No mock route for ${method} ${pathname}`, 404);
}

/** Test helper: reset the in-memory database. */
export function resetMockDb() {
  db = null;
}
