// The centralized API adapter. Every screen talks to the backend through the
// functions in this file, so when the backend's routes or shapes change there
// is exactly one place to adjust.
//
// Base paths follow the HubSpot CRM v3 API the backend is compatible with:
//   /crm/v3/objects/{type}             list, create
//   /crm/v3/objects/{type}/{id}        read, update
//   /crm/v3/objects/{type}/search      search with filters, sorts, query
//   /crm/v3/objects/{type}/batch/read  batch read
//   /crm/v3/pipelines/{type}           pipelines with stages
//   /crm/v3/lists/...                  lists and memberships
//   /crm/v4/objects/{type}/{id}/associations/{to}
//   /health, /__agente                 challenge-specific

import { call } from "./transport";
import type {
  Activity,
  AgentRequest,
  AgentResponse,
  Company,
  Contact,
  CrmUser,
  Deal,
  Engagement,
  EngagementType,
  Health,
  HsObject,
  LineItem,
  ListInfo,
  ListMembership,
  ObjectType,
  Paged,
  Pipeline,
  Product,
  Props,
  SearchRequest,
  Ticket,
} from "./types";

export const COMPANY_PROPS = [
  "name",
  "domain",
  "hs_additional_domains",
  "city",
  "state",
  "partita_iva",
  "fatturato_2025",
  "classe_cliente",
  "id_legacy",
  "createdate",
  "hs_lastmodifieddate",
  "phone",
  "description",
];

export const CONTACT_PROPS = [
  "firstname",
  "lastname",
  "email",
  "phone",
  "lifecyclestage",
  "jobtitle",
  "company",
  "associatedcompanyid",
  "id_legacy",
  "createdate",
  "lastmodifieddate",
];

export const DEAL_PROPS = [
  "dealname",
  "amount",
  "deal_currency_code",
  "pipeline",
  "dealstage",
  "closedate",
  "commerciale",
  "description",
  "id_legacy",
  "createdate",
  "hs_lastmodifieddate",
];

export const TICKET_PROPS = [
  "subject",
  "content",
  "hs_pipeline",
  "hs_pipeline_stage",
  "hs_ticket_priority",
  "createdate",
  "closed_date",
  "assegnatario",
  "id_legacy",
  "hs_lastmodifieddate",
];

export const LINE_ITEM_PROPS = [
  "name",
  "quantity",
  "price",
  "hs_discount_percentage",
  "amount",
  "hs_sku",
  "hs_product_id",
  "id_legacy",
];

export const PRODUCT_PROPS = ["name", "hs_sku", "price", "description"];

const ENGAGEMENT_PROPS: Record<EngagementType, string[]> = {
  notes: ["hs_timestamp", "hs_note_body", "autore", "id_legacy"],
  calls: ["hs_timestamp", "hs_call_body", "hs_call_title", "autore", "id_legacy"],
  emails: ["hs_timestamp", "hs_email_text", "hs_email_subject", "autore", "id_legacy"],
  meetings: ["hs_timestamp", "hs_meeting_body", "hs_meeting_title", "autore", "id_legacy"],
  tasks: ["hs_timestamp", "hs_task_subject", "hs_task_body", "hs_task_status", "autore", "id_legacy"],
};

const PROPS_BY_TYPE: Record<ObjectType, string[]> = {
  companies: COMPANY_PROPS,
  contacts: CONTACT_PROPS,
  deals: DEAL_PROPS,
  tickets: TICKET_PROPS,
  products: PRODUCT_PROPS,
  line_items: LINE_ITEM_PROPS,
  notes: ENGAGEMENT_PROPS.notes,
  calls: ENGAGEMENT_PROPS.calls,
  emails: ENGAGEMENT_PROPS.emails,
  meetings: ENGAGEMENT_PROPS.meetings,
  tasks: ENGAGEMENT_PROPS.tasks,
};

// HubSpot object type ids, used by the lists API.
export const OBJECT_TYPE_IDS: Record<"companies" | "contacts" | "deals" | "tickets", string> = {
  contacts: "0-1",
  companies: "0-2",
  deals: "0-3",
  tickets: "0-5",
};

export const DORMANT_LIST_NAME = "Clienti dormienti";

// ---------- generic object access ----------

export function getObject<T extends HsObject>(
  type: ObjectType,
  id: string,
  opts: { associations?: ObjectType[]; properties?: string[] } = {},
) {
  return call<T>(`/crm/v3/objects/${type}/${encodeURIComponent(id)}`, {
    query: {
      properties: opts.properties ?? PROPS_BY_TYPE[type],
      associations: opts.associations,
    },
  });
}

export function listObjects<T extends HsObject>(
  type: ObjectType,
  opts: { limit?: number; after?: string; properties?: string[]; associations?: ObjectType[] } = {},
) {
  return call<Paged<T>>(`/crm/v3/objects/${type}`, {
    query: {
      limit: opts.limit ?? 50,
      after: opts.after,
      properties: opts.properties ?? PROPS_BY_TYPE[type],
      associations: opts.associations,
    },
  });
}

export function searchObjects<T extends HsObject>(type: ObjectType, body: SearchRequest) {
  return call<Paged<T>>(`/crm/v3/objects/${type}/search`, {
    method: "POST",
    body: { properties: PROPS_BY_TYPE[type], limit: 50, ...body },
  });
}

export async function batchRead<T extends HsObject>(type: ObjectType, ids: string[], properties?: string[]) {
  const unique = Array.from(new Set(ids.filter(Boolean)));
  if (unique.length === 0) return [] as T[];
  const out: T[] = [];
  // HubSpot caps batch reads at 100 inputs.
  for (let i = 0; i < unique.length; i += 100) {
    const chunk = unique.slice(i, i + 100);
    const res = await call<{ results: T[] }>(`/crm/v3/objects/${type}/batch/read`, {
      method: "POST",
      body: { properties: properties ?? PROPS_BY_TYPE[type], inputs: chunk.map((id) => ({ id })) },
    });
    out.push(...(res.results ?? []));
  }
  return out;
}

export function updateObject<T extends HsObject>(type: ObjectType, id: string, properties: Props) {
  return call<T>(`/crm/v3/objects/${type}/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: { properties },
  });
}

export function createObject<T extends HsObject>(
  type: ObjectType,
  properties: Props,
  associations?: Array<{ to: { id: string }; types: Array<{ associationCategory: string; associationTypeId: number }> }>,
) {
  return call<T>(`/crm/v3/objects/${type}`, {
    method: "POST",
    body: associations ? { properties, associations } : { properties },
  });
}

/** Ids of the records of `to` associated with `type/id`. Uses the association
 *  payload on the object when present, otherwise the v4 associations endpoint. */
export async function associatedIds(obj: HsObject, type: ObjectType, to: ObjectType): Promise<string[]> {
  const inline = obj.associations?.[to]?.results ?? obj.associations?.[singular(to)]?.results;
  if (inline) return Array.from(new Set(inline.map((r) => String(r.id))));
  try {
    const res = await call<{ results: Array<{ toObjectId: string | number }> }>(
      `/crm/v4/objects/${type}/${encodeURIComponent(obj.id)}/associations/${to}`,
      { query: { limit: 500 } },
    );
    return Array.from(new Set((res.results ?? []).map((r) => String(r.toObjectId))));
  } catch {
    return [];
  }
}

const SINGULAR: Record<ObjectType, string> = {
  companies: "company",
  contacts: "contact",
  deals: "deal",
  tickets: "ticket",
  products: "product",
  line_items: "line_item",
  notes: "note",
  calls: "call",
  emails: "email",
  meetings: "meeting",
  tasks: "task",
};

function singular(type: ObjectType): string {
  return SINGULAR[type];
}

// ---------- companies ----------

export interface CompanyListParams {
  query?: string;
  classe?: string;
  state?: string;
  sortBy?: "name" | "fatturato_2025" | "hs_lastmodifieddate" | "city";
  sortDir?: "ASCENDING" | "DESCENDING";
  after?: string;
  limit?: number;
}

export function listCompanies(params: CompanyListParams = {}) {
  const filters = [];
  if (params.classe) filters.push({ propertyName: "classe_cliente", operator: "EQ" as const, value: params.classe });
  if (params.state) filters.push({ propertyName: "state", operator: "EQ" as const, value: params.state });
  return searchObjects<Company>("companies", {
    query: params.query?.trim() || undefined,
    filterGroups: filters.length ? [{ filters }] : undefined,
    sorts: [{ propertyName: params.sortBy ?? "name", direction: params.sortDir ?? "ASCENDING" }],
    limit: params.limit ?? 50,
    after: params.after,
  });
}

export async function getCompanyPage(id: string) {
  const company = await getObject<Company>("companies", id, {
    associations: ["contacts", "deals", "tickets"],
  });
  const [contactIds, dealIds, ticketIds] = await Promise.all([
    associatedIds(company, "companies", "contacts"),
    associatedIds(company, "companies", "deals"),
    associatedIds(company, "companies", "tickets"),
  ]);
  const [contacts, deals, tickets] = await Promise.all([
    batchRead<Contact>("contacts", contactIds),
    batchRead<Deal>("deals", dealIds),
    batchRead<Ticket>("tickets", ticketIds),
  ]);
  return { company, contacts, deals, tickets };
}

// ---------- contacts ----------

export interface ContactListParams {
  query?: string;
  lifecyclestage?: string;
  after?: string;
  limit?: number;
}

export function listContacts(params: ContactListParams = {}) {
  const filters = [];
  if (params.lifecyclestage)
    filters.push({ propertyName: "lifecyclestage", operator: "EQ" as const, value: params.lifecyclestage });
  return searchObjects<Contact>("contacts", {
    query: params.query?.trim() || undefined,
    filterGroups: filters.length ? [{ filters }] : undefined,
    sorts: [{ propertyName: "lastname", direction: "ASCENDING" }],
    limit: params.limit ?? 50,
    after: params.after,
  });
}

export async function getContactPage(id: string) {
  const contact = await getObject<Contact>("contacts", id, { associations: ["companies", "deals", "tickets"] });
  const [companyIds, dealIds, ticketIds] = await Promise.all([
    associatedIds(contact, "contacts", "companies"),
    associatedIds(contact, "contacts", "deals"),
    associatedIds(contact, "contacts", "tickets"),
  ]);
  const [companies, deals, tickets] = await Promise.all([
    batchRead<Company>("companies", companyIds),
    batchRead<Deal>("deals", dealIds),
    batchRead<Ticket>("tickets", ticketIds),
  ]);
  return { contact, companies, deals, tickets };
}

// ---------- pipelines ----------

export async function getPipelines(type: "deals" | "tickets"): Promise<Pipeline[]> {
  const res = await call<{ results: Pipeline[] }>(`/crm/v3/pipelines/${type}`);
  const pipelines = (res.results ?? []).slice().sort((a, b) => (a.displayOrder ?? 0) - (b.displayOrder ?? 0));
  for (const p of pipelines) p.stages = (p.stages ?? []).slice().sort((a, b) => (a.displayOrder ?? 0) - (b.displayOrder ?? 0));
  return pipelines;
}

// ---------- deals ----------

export const BOARD_COLUMN_LIMIT = 40;

export function dealsInStage(pipelineId: string, stageId: string, opts: { after?: string; limit?: number } = {}) {
  return searchObjects<Deal>("deals", {
    filterGroups: [
      {
        filters: [
          { propertyName: "pipeline", operator: "EQ", value: pipelineId },
          { propertyName: "dealstage", operator: "EQ", value: stageId },
        ],
      },
    ],
    sorts: [{ propertyName: "hs_lastmodifieddate", direction: "DESCENDING" }],
    limit: opts.limit ?? BOARD_COLUMN_LIMIT,
    after: opts.after,
  });
}

export function moveDeal(id: string, stageId: string) {
  return updateObject<Deal>("deals", id, { dealstage: stageId });
}

export async function getDealPage(id: string) {
  const deal = await getObject<Deal>("deals", id, { associations: ["companies", "contacts", "line_items", "tickets"] });
  const [companyIds, contactIds, lineItemIds, ticketIds] = await Promise.all([
    associatedIds(deal, "deals", "companies"),
    associatedIds(deal, "deals", "contacts"),
    associatedIds(deal, "deals", "line_items"),
    associatedIds(deal, "deals", "tickets"),
  ]);
  const [companies, contacts, lineItems, tickets] = await Promise.all([
    batchRead<Company>("companies", companyIds),
    batchRead<Contact>("contacts", contactIds),
    batchRead<LineItem>("line_items", lineItemIds),
    batchRead<Ticket>("tickets", ticketIds),
  ]);
  const productIds = lineItems.map((li) => li.properties.hs_product_id).filter((x): x is string => Boolean(x));
  const products = productIds.length ? await batchRead<Product>("products", productIds) : [];
  return { deal, companies, contacts, lineItems, products, tickets };
}

export interface DealListParams {
  query?: string;
  pipeline?: string;
  stage?: string;
  owner?: string;
  after?: string;
  limit?: number;
}

export function listDeals(params: DealListParams = {}) {
  const filters = [];
  if (params.pipeline) filters.push({ propertyName: "pipeline", operator: "EQ" as const, value: params.pipeline });
  if (params.stage) filters.push({ propertyName: "dealstage", operator: "EQ" as const, value: params.stage });
  if (params.owner) filters.push({ propertyName: "commerciale", operator: "EQ" as const, value: params.owner });
  return searchObjects<Deal>("deals", {
    query: params.query?.trim() || undefined,
    filterGroups: filters.length ? [{ filters }] : undefined,
    sorts: [{ propertyName: "hs_lastmodifieddate", direction: "DESCENDING" }],
    limit: params.limit ?? 50,
    after: params.after,
  });
}

// ---------- tickets ----------

export interface TicketListParams {
  query?: string;
  stage?: string;
  priority?: string;
  owner?: string;
  openOnly?: boolean;
  closedStageIds?: string[];
  after?: string;
  limit?: number;
  sortBy?: "createdate" | "hs_lastmodifieddate" | "hs_ticket_priority";
  sortDir?: "ASCENDING" | "DESCENDING";
}

export function listTickets(params: TicketListParams = {}) {
  const filters = [];
  if (params.stage) filters.push({ propertyName: "hs_pipeline_stage", operator: "EQ" as const, value: params.stage });
  if (params.priority) filters.push({ propertyName: "hs_ticket_priority", operator: "EQ" as const, value: params.priority });
  if (params.owner) filters.push({ propertyName: "assegnatario", operator: "EQ" as const, value: params.owner });
  if (params.openOnly && params.closedStageIds?.length)
    filters.push({ propertyName: "hs_pipeline_stage", operator: "NOT_IN" as const, values: params.closedStageIds });
  return searchObjects<Ticket>("tickets", {
    query: params.query?.trim() || undefined,
    filterGroups: filters.length ? [{ filters }] : undefined,
    sorts: [{ propertyName: params.sortBy ?? "createdate", direction: params.sortDir ?? "DESCENDING" }],
    limit: params.limit ?? 50,
    after: params.after,
  });
}

export async function getTicketPage(id: string) {
  const ticket = await getObject<Ticket>("tickets", id, { associations: ["companies", "contacts", "deals"] });
  const [companyIds, contactIds, dealIds] = await Promise.all([
    associatedIds(ticket, "tickets", "companies"),
    associatedIds(ticket, "tickets", "contacts"),
    associatedIds(ticket, "tickets", "deals"),
  ]);
  const [companies, contacts, deals] = await Promise.all([
    batchRead<Company>("companies", companyIds),
    batchRead<Contact>("contacts", contactIds),
    batchRead<Deal>("deals", dealIds),
  ]);
  return { ticket, companies, contacts, deals };
}

export function updateTicket(id: string, properties: Props) {
  return updateObject<Ticket>("tickets", id, properties);
}

// ---------- lists (dormant customers) ----------

export async function findListByName(objectTypeId: string, name: string): Promise<ListInfo | null> {
  try {
    const res = await call<{ list: ListInfo }>(
      `/crm/v3/lists/object-type-id/${objectTypeId}/name/${encodeURIComponent(name)}`,
    );
    return res.list ?? null;
  } catch (err) {
    if (err instanceof Error && "status" in err && (err as { status: number }).status === 404) return null;
    throw err;
  }
}

export function listMemberships(listId: string, opts: { after?: string; limit?: number } = {}) {
  return call<Paged<ListMembership>>(`/crm/v3/lists/${encodeURIComponent(listId)}/memberships`, {
    query: { limit: opts.limit ?? 250, after: opts.after },
  });
}

export async function getDormantCompanies(opts: { after?: string; limit?: number } = {}) {
  const list = await findListByName(OBJECT_TYPE_IDS.companies, DORMANT_LIST_NAME);
  if (!list) return { list: null, companies: [] as Company[], paging: undefined as Paged<unknown>["paging"], total: 0 };
  const page = await listMemberships(list.listId, opts);
  const companies = await batchRead<Company>(
    "companies",
    (page.results ?? []).map((m) => String(m.recordId)),
  );
  // Keep the membership order.
  const order = new Map((page.results ?? []).map((m, i) => [String(m.recordId), i]));
  companies.sort((a, b) => (order.get(a.id) ?? 0) - (order.get(b.id) ?? 0));
  return { list, companies, paging: page.paging, total: page.total };
}

// ---------- activities ----------

function toActivity(kind: EngagementType, e: Engagement): Activity {
  const p = e.properties;
  const title =
    kind === "calls"
      ? p.hs_call_title
      : kind === "emails"
        ? p.hs_email_subject
        : kind === "meetings"
          ? p.hs_meeting_title
          : kind === "tasks"
            ? p.hs_task_subject
            : null;
  const body =
    (kind === "notes" && p.hs_note_body) ||
    (kind === "calls" && p.hs_call_body) ||
    (kind === "emails" && p.hs_email_text) ||
    (kind === "meetings" && p.hs_meeting_body) ||
    (kind === "tasks" && p.hs_task_body) ||
    "";
  return {
    id: `${kind}:${e.id}`,
    kind,
    timestamp: p.hs_timestamp ?? e.createdAt ?? null,
    title: title ?? null,
    body: body ?? "",
    author: p.autore ?? null,
    status: p.hs_task_status ?? null,
    raw: e,
  };
}

const ACTIVITY_KINDS: EngagementType[] = ["notes", "calls", "emails", "meetings", "tasks"];

/**
 * Activities associated with any of the given records, newest first. Uses the
 * `associations.<object>` search filter the HubSpot search API documents.
 */
export async function activitiesFor(targets: Array<{ type: "contacts" | "deals" | "companies" | "tickets"; ids: string[] }>) {
  const groups = targets
    .filter((t) => t.ids.length > 0)
    .map((t) => ({
      filters: [{ propertyName: `associations.${singular(t.type)}`, operator: "IN" as const, values: t.ids.slice(0, 100) }],
    }));
  if (groups.length === 0) return [] as Activity[];
  const perKind = await Promise.all(
    ACTIVITY_KINDS.map(async (kind) => {
      try {
        const res = await searchObjects<Engagement>(kind, {
          filterGroups: groups,
          sorts: [{ propertyName: "hs_timestamp", direction: "DESCENDING" }],
          limit: 100,
        });
        return (res.results ?? []).map((e) => toActivity(kind, e));
      } catch {
        return [] as Activity[];
      }
    }),
  );
  const seen = new Set<string>();
  return perKind
    .flat()
    .filter((a) => (seen.has(a.id) ? false : (seen.add(a.id), true)))
    .sort((a, b) => (Date.parse(b.timestamp ?? "") || 0) - (Date.parse(a.timestamp ?? "") || 0));
}

// HubSpot-defined association type ids for notes.
const NOTE_ASSOCIATION: Record<"companies" | "contacts" | "deals" | "tickets", number> = {
  contacts: 202,
  companies: 190,
  deals: 214,
  tickets: 228,
};

export function createNote(
  body: string,
  author: string | null,
  target: { type: "companies" | "contacts" | "deals" | "tickets"; id: string },
) {
  return createObject<Engagement>(
    "notes",
    {
      hs_timestamp: new Date().toISOString(),
      hs_note_body: body,
      ...(author ? { autore: author } : {}),
    },
    [
      {
        to: { id: target.id },
        types: [{ associationCategory: "HUBSPOT_DEFINED", associationTypeId: NOTE_ASSOCIATION[target.type] }],
      },
    ],
  );
}

// ---------- dashboard counts ----------

export async function countObjects(type: ObjectType, filters: SearchRequest["filterGroups"] = undefined) {
  const res = await searchObjects<HsObject>(type, { filterGroups: filters, limit: 1, properties: ["hs_object_id"] });
  return res.total ?? res.results?.length ?? 0;
}

export function recentDeals(limit = 8) {
  return searchObjects<Deal>("deals", {
    sorts: [{ propertyName: "hs_lastmodifieddate", direction: "DESCENDING" }],
    limit,
  });
}

export function recentTickets(limit = 8) {
  return searchObjects<Ticket>("tickets", {
    sorts: [{ propertyName: "createdate", direction: "DESCENDING" }],
    limit,
  });
}

export function topCompanies(limit = 8) {
  return searchObjects<Company>("companies", {
    filterGroups: [{ filters: [{ propertyName: "fatturato_2025", operator: "GT", value: "0" }] }],
    sorts: [{ propertyName: "fatturato_2025", direction: "DESCENDING" }],
    limit,
  });
}

// ---------- owners (Brambilla's users, from utenti.csv) ----------

interface OwnerRecord {
  id: string;
  email?: string | null;
  firstName?: string | null;
  lastName?: string | null;
  role?: string | null;
  archived?: boolean;
  active?: boolean;
}

export async function listOwners(): Promise<CrmUser[]> {
  const res = await call<{ results: OwnerRecord[] }>("/crm/v3/owners", { query: { limit: 500 } });
  return (res.results ?? [])
    .filter((o) => o.email && !o.archived && o.active !== false)
    .map((o) => ({
      email: o.email!.trim().toLowerCase(),
      name: [o.firstName, o.lastName].filter(Boolean).join(" ").trim() || o.email!,
      role: o.role ?? undefined,
    }))
    .sort((a, b) => a.name.localeCompare(b.name, "en"));
}

// ---------- health and assistant ----------

export function getHealth() {
  return call<Health>("/health", { anonymous: true });
}

/**
 * The bare contract returns exactly `{reply}`. With `?trace=1` the backend may
 * add a bounded sanitized `trace` envelope; the chat shows it only when the
 * user has enabled Assistant Insights.
 */
export function askAssistant(body: AgentRequest, signal?: AbortSignal, includeTrace = false) {
  return call<AgentResponse>("/__agente", { method: "POST", body, signal, query: includeTrace ? { trace: 1 } : undefined });
}
