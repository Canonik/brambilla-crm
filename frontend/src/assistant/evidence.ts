import type {
  AssistantEvidenceEvent,
  EvidenceCalculation,
  EvidenceOperation,
  EvidenceRecord,
  EvidenceStatus,
  ObjectType,
} from "@/api/types";

// Projection of the sanitized v1 trace envelope the backend attaches to a
// reply when the user asked for evidence. Everything here is behavioral
// provenance: what the tool dispatcher observed, never model internals.

export const EVIDENCE_TOOLS: Record<string, { label: string; operation: EvidenceOperation }> = {
  search_companies: { label: "Searched companies", operation: "read" },
  search_contacts: { label: "Searched contacts", operation: "read" },
  search_deals: { label: "Searched deals", operation: "read" },
  search_tickets: { label: "Searched tickets", operation: "read" },
  get_record: { label: "Retrieved a CRM record", operation: "read" },
  company_overview: { label: "Retrieved company overview", operation: "read" },
  list_activities: { label: "Retrieved activities", operation: "read" },
  revenue: { label: "Calculated revenue", operation: "read" },
  deal_stats: { label: "Calculated deal statistics", operation: "read" },
  my_customers: { label: "Retrieved assigned customers", operation: "read" },
  list_users: { label: "Retrieved active users", operation: "read" },
  pipelines: { label: "Retrieved pipelines", operation: "read" },
  dormant_list: { label: "Retrieved dormant customers", operation: "read" },
  find_by_legacy_id: { label: "Looked up a Sinergia legacy id", operation: "read" },
  search_products: { label: "Searched the price list", operation: "read" },
  list_deal_line_items: { label: "Retrieved deal line items", operation: "read" },
  preview_attachment: { label: "Previewed a CSV attachment", operation: "read" },
  create_record: { label: "Created a CRM record", operation: "write" },
  update_record: { label: "Updated a CRM record", operation: "write" },
  associate: { label: "Associated CRM records", operation: "write" },
  dissociate: { label: "Removed a CRM association", operation: "write" },
  archive_record: { label: "Archived a CRM record", operation: "write" },
  create_records_bulk: { label: "Created CRM records in bulk", operation: "write" },
  import_attachment: { label: "Imported a CSV attachment", operation: "write" },
};

export type EvidenceFailure = "validation" | "not_found" | "conflict" | "rate_limited" | "rejected" | "error";
export const FAILURE_LABELS: Record<EvidenceFailure, string> = {
  validation: "rejected as invalid by the CRM",
  not_found: "record not found",
  conflict: "refused because it conflicts with an existing record",
  rate_limited: "rate limited",
  rejected: "refused by a CRM rule",
  error: "failed",
};

export interface EvidenceRelation {
  from: EvidenceRecord;
  to: EvidenceRecord;
}

const TYPES = new Set<ObjectType>(["companies", "contacts", "deals", "tickets", "products", "line_items", "notes", "calls", "emails", "meetings", "tasks"]);
const READ = new Set<EvidenceStatus>(["attempted", "completed", "failed"]);
const WRITE = new Set<EvidenceStatus>(["attempted", "awaiting_commit", "committed", "rolled_back", "unknown"]);
const FAILURES = new Set<EvidenceFailure>(["validation", "not_found", "conflict", "rate_limited", "rejected", "error"]);
const SETTLED = new Set<EvidenceStatus>(["completed", "failed", "committed", "rolled_back", "unknown"]);
const MONEY = /^-?(?:0|[1-9][0-9]{0,13})\.[0-9]{2}$/;
const ID = /^[1-9][0-9]{0,19}$/;
const MAX_COUNT = 1_000_000;

export interface ProjectedEvidenceEvent extends Omit<AssistantEvidenceEvent, "records" | "calculation"> {
  label: string;
  records: EvidenceRecord[];
  relations: EvidenceRelation[];
  count?: number;
  total?: number;
  failure?: EvidenceFailure;
  calculation?: EvidenceCalculation;
}

export interface ProjectedEvidence {
  events: ProjectedEvidenceEvent[];
  incomplete: boolean;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function recordKey(record: EvidenceRecord): string {
  return `${record.type}:${record.id}`;
}

function record(value: unknown): EvidenceRecord | null {
  if (!isObject(value) || !TYPES.has(value.type as ObjectType) || typeof value.id !== "string" || !ID.test(value.id)) return null;
  return { type: value.type as ObjectType, id: value.id };
}

function count(value: unknown): number | undefined {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 && value <= MAX_COUNT ? value : undefined;
}

function calculation(value: unknown): EvidenceCalculation | undefined {
  if (!isObject(value) || value.kind !== "sum_money_v1" || value.currency !== "EUR" ||
      typeof value.populationComplete !== "boolean" || !Number.isSafeInteger(value.populationCount) ||
      !Array.isArray(value.terms) || value.terms.length > 20 || typeof value.result !== "string" || !MONEY.test(value.result)) return undefined;
  const terms: EvidenceCalculation["terms"] = [];
  for (const raw of value.terms) {
    if (!isObject(raw) || typeof raw.amount !== "string" || !MONEY.test(raw.amount)) return undefined;
    const ref = record(raw.record);
    if (!ref) return undefined;
    terms.push({ record: ref, amount: raw.amount });
  }
  if ((value.populationComplete && value.populationCount !== terms.length) || (value.populationCount as number) < terms.length) return undefined;
  return {
    kind: "sum_money_v1", currency: "EUR", populationComplete: value.populationComplete,
    populationCount: value.populationCount as number, terms, result: value.result,
    ...(typeof value.policy === "string" && value.policy.length <= 80 ? { policy: value.policy } : {}),
    ...(Number.isSafeInteger(value.year) ? { year: value.year as number } : {}),
  };
}

export function projectEvidence(value: unknown): ProjectedEvidence | null {
  if (!isObject(value) || value.version !== 1 || !Array.isArray(value.events) || typeof value.incomplete !== "boolean") return null;
  const projected: ProjectedEvidence = { events: [], incomplete: value.incomplete || value.events.length > 64 };
  let last = 0;
  for (const raw of value.events.slice(0, 64)) {
    if (!isObject(raw) || typeof raw.tool !== "string") { projected.incomplete = true; continue; }
    const config = EVIDENCE_TOOLS[raw.tool];
    const op = raw.operation as EvidenceOperation;
    const status = raw.status as EvidenceStatus;
    if (!config || config.operation !== op || !(op === "read" ? READ : WRITE).has(status) ||
        !Number.isSafeInteger(raw.sequence) || (raw.sequence as number) <= last || !Number.isSafeInteger(raw.call)) {
      projected.incomplete = true;
      continue;
    }
    last = raw.sequence as number;
    const records: EvidenceRecord[] = [];
    const present = new Set<string>();
    if (Array.isArray(raw.records)) for (const item of raw.records.slice(0, 20)) {
      const safe = record(item);
      if (safe && !present.has(recordKey(safe))) { records.push(safe); present.add(recordKey(safe)); }
      else projected.incomplete = true;
    }
    // A relation is accepted only between records this same event vouches for.
    const relations: EvidenceRelation[] = [];
    if (Array.isArray(raw.relations)) for (const item of raw.relations.slice(0, 40)) {
      const from = isObject(item) ? record(item.from) : null;
      const to = isObject(item) ? record(item.to) : null;
      if (from && to && present.has(recordKey(from)) && present.has(recordKey(to)) && recordKey(from) !== recordKey(to)) relations.push({ from, to });
      else projected.incomplete = true;
    }
    const event: ProjectedEvidenceEvent = {
      sequence: raw.sequence as number, call: raw.call as number, tool: raw.tool, label: config.label,
      operation: op, status, records, relations,
    };
    if (typeof raw.durationMs === "number" && Number.isFinite(raw.durationMs) && raw.durationMs >= 0 && raw.durationMs <= 60_000) event.durationMs = Math.round(raw.durationMs);
    if (typeof raw.inputSummary === "string" && raw.inputSummary.length <= 160) event.inputSummary = raw.inputSummary;
    const rows = count(raw.count);
    if (rows !== undefined) event.count = rows;
    const total = count(raw.total);
    if (total !== undefined && (rows === undefined || total >= rows)) event.total = total;
    if (FAILURES.has(raw.failure as EvidenceFailure) && (status === "failed" || status === "rolled_back" || status === "unknown")) event.failure = raw.failure as EvidenceFailure;
    const calc = calculation(raw.calculation);
    if (calc && op === "read" && status === "completed") event.calculation = calc;
    projected.events.push(event);
  }
  return projected;
}

export function evidenceRecordLink(record: EvidenceRecord): string | null {
  return ["companies", "contacts", "deals", "tickets"].includes(record.type) ? `/${record.type}/${record.id}` : null;
}

// ---------------------------------------------------------------------------
// Insights: one row per tool call, the records and links they vouch for, and
// the limitations that follow from what was (and was not) observed.

export interface InsightCall {
  call: number;
  step: number;
  tool: string;
  label: string;
  operation: EvidenceOperation;
  status: EvidenceStatus;
  history: EvidenceStatus[];
  settled: boolean;
  durationMs?: number;
  inputSummary?: string;
  records: EvidenceRecord[];
  relations: EvidenceRelation[];
  count?: number;
  total?: number;
  failure?: EvidenceFailure;
  calculation?: EvidenceCalculation;
}

export interface InsightRecord extends EvidenceRecord {
  key: string;
  /** Step of the first call that referenced this record. */
  firstStep: number;
  /** Steps of every call that referenced it. */
  steps: number[];
  written: boolean;
}

export interface InsightLimitation {
  /** Observed: follows directly from trace events. Interpretation: a reading of them. */
  basis: "observed" | "interpretation";
  tone: "warn" | "bad" | "muted" | "brand";
  text: string;
  step?: number;
}

export type InsightVerdict = "complete" | "partial" | "none";

export interface Insights {
  calls: InsightCall[];
  records: InsightRecord[];
  relations: EvidenceRelation[];
  calculation?: InsightCall;
  limitations: InsightLimitation[];
  verdict: InsightVerdict;
  incomplete: boolean;
  reads: number;
  writes: number;
  committed: number;
  rolledBack: number;
  /** Calls that settled without success: failed reads, rolled back or unknown writes. */
  unsuccessful: number;
  totalMs: number;
}

export function deriveInsights(evidence: ProjectedEvidence): Insights {
  const byCall = new Map<number, InsightCall>();
  for (const event of evidence.events) {
    let call = byCall.get(event.call);
    if (!call) {
      call = {
        call: event.call, step: byCall.size + 1, tool: event.tool, label: event.label, operation: event.operation,
        status: event.status, history: [], settled: false, records: [], relations: [],
      };
      byCall.set(event.call, call);
    }
    call.history.push(event.status);
    call.status = event.status;
    call.settled = SETTLED.has(event.status);
    if (event.durationMs !== undefined) call.durationMs = event.durationMs;
    if (event.inputSummary) call.inputSummary = event.inputSummary;
    if (event.records.length) call.records = event.records;
    if (event.relations.length) call.relations = event.relations;
    if (event.count !== undefined) call.count = event.count;
    if (event.total !== undefined) call.total = event.total;
    if (event.failure) call.failure = event.failure;
    if (event.calculation) call.calculation = event.calculation;
  }
  const calls = [...byCall.values()];

  const records = new Map<string, InsightRecord>();
  const relations: EvidenceRelation[] = [];
  const linked = new Set<string>();
  for (const call of calls) {
    for (const item of call.records) {
      const key = recordKey(item);
      const known = records.get(key);
      if (known) known.steps.push(call.step);
      else records.set(key, { ...item, key, firstStep: call.step, steps: [call.step], written: false });
      if (call.operation === "write" && call.status === "committed") records.get(key)!.written = true;
    }
    for (const relation of call.relations) {
      const a = recordKey(relation.from), b = recordKey(relation.to);
      if (linked.has(`${a}|${b}`) || linked.has(`${b}|${a}`)) continue;
      linked.add(`${a}|${b}`);
      relations.push(relation);
    }
  }

  const reads = calls.filter((call) => call.operation === "read").length;
  const writes = calls.filter((call) => call.operation === "write").length;
  const committed = calls.filter((call) => call.status === "committed").length;
  const rolledBack = calls.filter((call) => call.status === "rolled_back").length;
  const unsuccessful = calls.filter((call) => call.status === "failed" || call.status === "rolled_back" || call.status === "unknown").length;
  const totalMs = calls.reduce((sum, call) => sum + (call.durationMs ?? 0), 0);
  const unresolved = calls.some((call) => !call.settled || call.status === "unknown");
  const verdict: InsightVerdict = calls.length === 0 ? "none" : evidence.incomplete || unresolved ? "partial" : "complete";

  const limitations: InsightLimitation[] = [];
  if (calls.length === 0) {
    limitations.push({ basis: "observed", tone: "muted", text: "No CRM operation was observed for this reply. The assistant answered from the conversation alone, for example to greet you or to ask a clarifying question." });
  }
  for (const call of calls) {
    const step = call.step;
    if (call.operation === "read" && call.status === "completed" && call.count === 0) {
      limitations.push({ basis: "observed", tone: "warn", step, text: `${call.label} returned no matching records${call.inputSummary ? ` (${call.inputSummary})` : ""}.` });
    }
    if (call.operation === "read" && call.status === "completed" && call.count !== undefined && call.total !== undefined && call.total > call.count) {
      limitations.push({ basis: "observed", tone: "muted", step, text: `${call.label}: ${call.count} of ${call.total} matching records were retrieved; the rest were not read.` });
    }
    if (call.status === "failed") {
      limitations.push({ basis: "observed", tone: "bad", step, text: `${call.label} ${FAILURE_LABELS[call.failure ?? "error"]}; no data from this step reached the reply.` });
    }
    if (call.status === "rolled_back") {
      limitations.push({ basis: "observed", tone: "bad", step, text: `${call.label} was ${FAILURE_LABELS[call.failure ?? "error"]} and rolled back; the CRM is unchanged for this step.` });
    }
    if (call.status === "unknown") {
      limitations.push({ basis: "observed", tone: "warn", step, text: `${call.label}: the transaction outcome could not be confirmed. Check the record before relying on the reply.` });
    }
    if (!call.settled) {
      limitations.push({ basis: "observed", tone: "warn", step, text: `${call.label} never settled; the trace ends before its outcome was recorded.` });
    }
  }
  if (evidence.incomplete) {
    limitations.push({ basis: "observed", tone: "warn", text: "The trace is partial: some events, records or links were dropped to stay within the evidence budget, or an event failed validation." });
  }
  // Interpretation: several candidates retrieved, none referenced again.
  for (const call of calls) {
    if (call.operation !== "read" || call.status !== "completed" || (call.count ?? call.records.length) < 2 || !call.tool.startsWith("search_")) continue;
    const later = calls.filter((other) => other.step > call.step);
    const reused = later.some((other) => other.records.some((item) => call.records.some((mine) => recordKey(mine) === recordKey(item))));
    if (!reused && later.length === 0) {
      limitations.push({ basis: "interpretation", tone: "brand", step: call.step, text: `${call.label} found ${call.count ?? call.records.length} candidates and the conversation stopped there. A likely reading is that the assistant asked you which one you meant.` });
    }
  }
  if (calls.length > 0) {
    limitations.push({ basis: "interpretation", tone: "muted", text: "A retrieved record was available to the model; this does not prove it shaped the wording of the reply." });
  }
  if (writes > 0) {
    limitations.push({ basis: "observed", tone: "muted", text: "A confirmed commit means the transaction was durably written. Automations the CRM runs on its own rules (for example the ticket opened when a deal is won) are not separate steps here." });
  }

  return {
    calls, records: [...records.values()], relations,
    calculation: calls.find((call) => call.calculation),
    limitations, verdict, incomplete: evidence.incomplete,
    reads, writes, committed, rolledBack, unsuccessful, totalMs,
  };
}
