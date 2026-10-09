// Shapes of the HubSpot-compatible API the backend exposes. Everything the
// UI reads goes through these types so a backend change is a one-file fix in
// `endpoints.ts`.

export type Props = Record<string, string | null | undefined>;

export interface HsObject<P extends Props = Props> {
  id: string;
  properties: P;
  createdAt?: string;
  updatedAt?: string;
  archived?: boolean;
  associations?: Record<string, { results: Array<{ id: string; type?: string }> }>;
}

export interface Paging {
  next?: { after: string; link?: string };
}

export interface Paged<T> {
  results: T[];
  paging?: Paging;
  total?: number;
}

export type ObjectType =
  | "companies"
  | "contacts"
  | "deals"
  | "tickets"
  | "products"
  | "line_items"
  | "notes"
  | "calls"
  | "emails"
  | "meetings"
  | "tasks";

export type EngagementType = "notes" | "calls" | "emails" | "meetings" | "tasks";

export interface CompanyProps extends Props {
  name?: string | null;
  domain?: string | null;
  hs_additional_domains?: string | null;
  city?: string | null;
  state?: string | null;
  partita_iva?: string | null;
  fatturato_2025?: string | null;
  classe_cliente?: string | null;
  id_legacy?: string | null;
  createdate?: string | null;
  hs_lastmodifieddate?: string | null;
  phone?: string | null;
  description?: string | null;
  num_associated_contacts?: string | null;
}

export interface ContactProps extends Props {
  firstname?: string | null;
  lastname?: string | null;
  email?: string | null;
  phone?: string | null;
  lifecyclestage?: string | null;
  jobtitle?: string | null;
  company?: string | null;
  associatedcompanyid?: string | null;
  id_legacy?: string | null;
  createdate?: string | null;
  lastmodifieddate?: string | null;
}

export interface DealProps extends Props {
  dealname?: string | null;
  amount?: string | null;
  deal_currency_code?: string | null;
  pipeline?: string | null;
  dealstage?: string | null;
  closedate?: string | null;
  commerciale?: string | null;
  description?: string | null;
  id_legacy?: string | null;
  createdate?: string | null;
  hs_lastmodifieddate?: string | null;
}

export interface TicketProps extends Props {
  subject?: string | null;
  content?: string | null;
  hs_pipeline?: string | null;
  hs_pipeline_stage?: string | null;
  hs_ticket_priority?: string | null;
  createdate?: string | null;
  closed_date?: string | null;
  assegnatario?: string | null;
  id_legacy?: string | null;
  hs_lastmodifieddate?: string | null;
}

export interface LineItemProps extends Props {
  name?: string | null;
  quantity?: string | null;
  price?: string | null;
  hs_discount_percentage?: string | null;
  amount?: string | null;
  hs_sku?: string | null;
  hs_product_id?: string | null;
  id_legacy?: string | null;
}

export interface ProductProps extends Props {
  name?: string | null;
  hs_sku?: string | null;
  price?: string | null;
  description?: string | null;
}

export interface EngagementProps extends Props {
  hs_timestamp?: string | null;
  hs_note_body?: string | null;
  hs_call_body?: string | null;
  hs_call_title?: string | null;
  hs_email_text?: string | null;
  hs_email_subject?: string | null;
  hs_meeting_body?: string | null;
  hs_meeting_title?: string | null;
  hs_task_subject?: string | null;
  hs_task_body?: string | null;
  hs_task_status?: string | null;
  autore?: string | null;
  id_legacy?: string | null;
}

export type Company = HsObject<CompanyProps>;
export type Contact = HsObject<ContactProps>;
export type Deal = HsObject<DealProps>;
export type Ticket = HsObject<TicketProps>;
export type LineItem = HsObject<LineItemProps>;
export type Product = HsObject<ProductProps>;
export type Engagement = HsObject<EngagementProps>;

/** An activity as the UI renders it, regardless of which engagement object it came from. */
export interface Activity {
  id: string;
  kind: EngagementType;
  timestamp: string | null;
  title: string | null;
  body: string;
  author: string | null;
  status?: string | null;
  raw: Engagement;
}

export interface Stage {
  id: string;
  label: string;
  displayOrder: number;
  metadata?: { isClosed?: string | boolean; probability?: string | number; ticketState?: string };
}

export interface Pipeline {
  id: string;
  label: string;
  displayOrder: number;
  stages: Stage[];
}

export type FilterOperator =
  | "EQ"
  | "NEQ"
  | "LT"
  | "LTE"
  | "GT"
  | "GTE"
  | "BETWEEN"
  | "IN"
  | "NOT_IN"
  | "HAS_PROPERTY"
  | "NOT_HAS_PROPERTY"
  | "CONTAINS_TOKEN"
  | "NOT_CONTAINS_TOKEN";

export interface Filter {
  propertyName: string;
  operator: FilterOperator;
  value?: string;
  highValue?: string;
  values?: string[];
}

export interface Sort {
  propertyName: string;
  direction: "ASCENDING" | "DESCENDING";
}

export interface SearchRequest {
  filterGroups?: Array<{ filters: Filter[] }>;
  sorts?: Sort[];
  query?: string;
  properties?: string[];
  limit?: number;
  after?: string;
}

export interface ListInfo {
  listId: string;
  name: string;
  objectTypeId: string;
  processingType?: string;
  additionalProperties?: Record<string, string>;
}

export interface ListMembership {
  recordId: string;
  membershipTimestamp?: string;
}

export interface Health {
  status: string;
  version: string;
  ui: Record<string, string>;
}

export interface AgentAttachment {
  name: string;
  content_type: string;
  content: string;
}

export interface AgentMessage {
  role: "user" | "assistant";
  content: string;
  attachments?: AgentAttachment[];
}

export interface AgentRequest {
  context: { now: string; user: string };
  messages: AgentMessage[];
}

/**
 * The contract only promises `reply`. If the backend also returns a trace of
 * the tools it called, the chat shows it as provenance for the answer.
 */
export interface AgentResponse {
  reply: string;
  trace?: AgentTraceStep[];
  tools?: AgentTraceStep[];
}

export interface AgentTraceStep {
  tool?: string;
  name?: string;
  input?: unknown;
  args?: unknown;
  output?: unknown;
  result?: unknown;
  summary?: string;
}

export interface CrmUser {
  email: string;
  name: string;
  role?: string;
}
