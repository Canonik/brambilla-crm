import type {
  AssistantEvidenceEvent,
  EvidenceCalculation,
  EvidenceOperation,
  EvidenceRecord,
  EvidenceStatus,
  ObjectType,
} from "@/api/types";

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
  create_record: { label: "Created a CRM record", operation: "write" },
  update_record: { label: "Updated a CRM record", operation: "write" },
  associate: { label: "Associated CRM records", operation: "write" },
  dissociate: { label: "Removed a CRM association", operation: "write" },
  archive_record: { label: "Archived a CRM record", operation: "write" },
  create_records_bulk: { label: "Created CRM records in bulk", operation: "write" },
};

const TYPES = new Set<ObjectType>(["companies", "contacts", "deals", "tickets", "products", "line_items", "notes", "calls", "emails", "meetings", "tasks"]);
const READ = new Set<EvidenceStatus>(["attempted", "completed", "failed"]);
const WRITE = new Set<EvidenceStatus>(["attempted", "awaiting_commit", "committed", "rolled_back", "unknown"]);
const MONEY = /^-?(?:0|[1-9][0-9]{0,13})\.[0-9]{2}$/;
const ID = /^[1-9][0-9]{0,19}$/;

export interface ProjectedEvidenceEvent extends Omit<AssistantEvidenceEvent, "records" | "calculation"> {
  label: string;
  records: EvidenceRecord[];
  calculation?: EvidenceCalculation;
}

export interface ProjectedEvidence {
  events: ProjectedEvidenceEvent[];
  incomplete: boolean;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function record(value: unknown): EvidenceRecord | null {
  if (!isObject(value) || !TYPES.has(value.type as ObjectType) || typeof value.id !== "string" || !ID.test(value.id)) return null;
  return { type: value.type as ObjectType, id: value.id };
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
    if (Array.isArray(raw.records)) for (const item of raw.records.slice(0, 20)) {
      const safe = record(item);
      if (safe) records.push(safe); else projected.incomplete = true;
    }
    const event: ProjectedEvidenceEvent = {
      sequence: raw.sequence as number, call: raw.call as number, tool: raw.tool, label: config.label,
      operation: op, status, records,
    };
    if (typeof raw.durationMs === "number" && Number.isFinite(raw.durationMs) && raw.durationMs >= 0 && raw.durationMs <= 60_000) event.durationMs = Math.round(raw.durationMs);
    if (typeof raw.inputSummary === "string" && raw.inputSummary.length <= 160) event.inputSummary = raw.inputSummary;
    const calc = calculation(raw.calculation);
    if (calc && op === "read" && status === "completed") event.calculation = calc;
    projected.events.push(event);
  }
  return projected;
}

export function evidenceRecordLink(record: EvidenceRecord): string | null {
  return ["companies", "contacts", "deals", "tickets"].includes(record.type) ? `/${record.type}/${record.id}` : null;
}
