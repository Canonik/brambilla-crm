import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Calculator, Check, ChevronDown, CircleAlert, Database, ExternalLink, Route, ShieldCheck } from "lucide-react";
import type { AssistantEvidence, EvidenceRecord } from "@/api/types";
import { cn } from "@/lib/cn";
import { evidenceRecordLink, projectEvidence, type ProjectedEvidenceEvent } from "./evidence";

type Tab = "actions" | "evidence" | "calculation" | "limits";

const STATUS: Record<string, string> = {
  attempted: "Attempt observed",
  completed: "Read completed",
  failed: "Read failed",
  awaiting_commit: "Tool returned · commit unconfirmed",
  committed: "Transaction commit confirmed",
  rolled_back: "Rolled back",
  unknown: "Outcome unknown",
};

function cents(value: string): bigint {
  const negative = value.startsWith("-");
  const digits = (negative ? value.slice(1) : value).replace(".", "");
  const amount = BigInt(digits);
  return negative ? -amount : amount;
}

function money(value: string): string {
  const amount = Number(value);
  return Number.isFinite(amount)
    ? new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(amount)
    : `${value} EUR`;
}

function recordName(record: EvidenceRecord): string {
  return record.type.replace("_", " ").replace(/(^|\s)\S/g, (letter) => letter.toUpperCase());
}

function Actions({ events }: { events: ProjectedEvidenceEvent[] }) {
  return (
    <ol className="relative ml-2 border-l border-line pl-5">
      {events.map((event) => (
        <li key={event.sequence} className="relative pb-4 last:pb-0">
          <span
            className={cn(
              "absolute -left-[27px] top-0.5 inline-flex size-3 items-center justify-center rounded-full ring-4 ring-surface",
              event.status === "committed" || event.status === "completed" ? "bg-good" : event.status === "rolled_back" || event.status === "failed" ? "bg-bad" : event.status === "unknown" ? "bg-warn" : "bg-gentian",
            )}
          />
          <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
            <div>
              <p className="text-[12px] font-semibold text-ink">{event.label}</p>
              {event.inputSummary ? <p className="mt-0.5 text-[11px] text-ink-2">{event.inputSummary}</p> : null}
            </div>
            {event.durationMs !== undefined ? <span className="tnum text-[10px] text-ink-3">{event.durationMs} ms</span> : null}
          </div>
          <div className="mt-1 inline-flex items-center gap-1 rounded-sm bg-surface-2 px-1.5 py-0.5 text-[10px] font-medium text-ink-2">
            {event.status === "completed" || event.status === "committed" ? <Check className="size-2.5 text-good" aria-hidden /> : null}
            {STATUS[event.status] ?? event.status}
          </div>
        </li>
      ))}
    </ol>
  );
}

function Records({ records }: { records: EvidenceRecord[] }) {
  if (!records.length) return <p className="text-[12px] text-ink-2">No direct record references were included for this reply.</p>;
  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
      {records.map((record) => {
        const href = evidenceRecordLink(record);
        const content = (
          <>
            <span className="text-[9px] font-semibold uppercase tracking-[0.12em] text-ink-3">{recordName(record)}</span>
            <strong className="tnum mt-0.5 text-[13px] text-ink">#{record.id}</strong>
            <span className="mt-1 flex items-center gap-1 text-[10px] text-ink-2">
              Direct backend reference {href ? <ExternalLink className="size-2.5" aria-hidden /> : null}
            </span>
          </>
        );
        const classes = "rounded-md border border-line bg-surface-2 px-3 py-2 text-left hover:border-gentian-line";
        return href ? <Link key={`${record.type}:${record.id}`} to={href} className={classes}>{content}</Link> : <div key={`${record.type}:${record.id}`} className={classes}>{content}</div>;
      })}
    </div>
  );
}

function Calculation({ event }: { event?: ProjectedEvidenceEvent }) {
  const calculation = event?.calculation;
  if (!calculation) return <p className="text-[12px] text-ink-2">No deterministic calculation receipt is available for this reply.</p>;
  const computed = calculation.terms.reduce((sum, term) => sum + cents(term.amount), 0n);
  const matches = computed === cents(calculation.result);
  const complete = calculation.populationComplete && calculation.populationCount === calculation.terms.length;
  return (
    <div>
      <div className={cn("mb-3 inline-flex items-center gap-1.5 rounded-sm px-2 py-1 text-[10px] font-semibold", complete && matches ? "bg-good-soft text-good" : "bg-warn-soft text-warn")}>
        {complete && matches ? <Check className="size-3" aria-hidden /> : <CircleAlert className="size-3" aria-hidden />}
        {complete ? (matches ? "Displayed amounts match the declared result" : "Displayed amounts do not match") : "Displayed subtotal only"}
      </div>
      <div className="flex flex-wrap items-center gap-2 rounded-md bg-surface-2 px-3 py-2 font-mono text-[12px] text-ink-2">
        <span>{calculation.terms.length ? calculation.terms.map((term) => money(term.amount)).join(" + ") : money("0.00")}</span>
        <span>=</span>
        <strong className="text-[14px] text-ink">{money(calculation.result)}</strong>
      </div>
      <ul className="mt-2 divide-y divide-line border-y border-line text-[11px]">
        {calculation.terms.map((term) => (
          <li key={`${term.record.type}:${term.record.id}`} className="flex items-center justify-between gap-3 py-1.5">
            <span className="text-ink-2">{recordName(term.record)} #{term.record.id}</span>
            <strong className="tnum text-ink">{money(term.amount)}</strong>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[10px] leading-relaxed text-ink-3">Arithmetic of supplied terms only. Source selection and business rules are not independently verified by this view.</p>
    </div>
  );
}

function Limits({ hasWrite, incomplete }: { hasWrite: boolean; incomplete: boolean }) {
  return (
    <ul className="space-y-2 text-[11px] leading-relaxed text-ink-2">
      <li className="flex gap-2"><CircleAlert className="mt-0.5 size-3 shrink-0 text-warn" aria-hidden />Observed retrieval does not prove a record caused the model's answer.</li>
      <li className="flex gap-2"><ShieldCheck className="mt-0.5 size-3 shrink-0 text-gentian" aria-hidden />This view exposes behavioral provenance, never hidden chain-of-thought, prompts, activations, or neural confidence.</li>
      {hasWrite ? <li className="flex gap-2"><CircleAlert className="mt-0.5 size-3 shrink-0 text-warn" aria-hidden />A commit acknowledgement confirms the transaction outcome, not that every submitted value changed. Rule-driven side effects may be absent.</li> : null}
      {incomplete ? <li className="flex gap-2"><CircleAlert className="mt-0.5 size-3 shrink-0 text-warn" aria-hidden />This trace is partial or contains an unresolved outcome.</li> : null}
    </ul>
  );
}

export function EvidenceInspector({ value }: { value: AssistantEvidence }) {
  const evidence = useMemo(() => projectEvidence(value), [value]);
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<Tab>("actions");
  if (!evidence) return null;
  const records: EvidenceRecord[] = [];
  const seen = new Set<string>();
  for (const event of evidence.events) for (const item of event.records) {
    const key = `${item.type}:${item.id}`;
    if (!seen.has(key)) { seen.add(key); records.push(item); }
  }
  const calculation = evidence.events.find((event) => event.calculation);
  const hasWrite = evidence.events.some((event) => event.operation === "write");
  const latestByCall = new Map<number, ProjectedEvidenceEvent>();
  for (const event of evidence.events) latestByCall.set(event.call, event);
  const unresolved = evidence.events.length === 0 || evidence.incomplete || [...latestByCall.values()].some((event) => event.status === "unknown" || event.status === "awaiting_commit" || event.status === "attempted");
  const tabs: Array<{ id: Tab; label: string; icon: typeof Route }> = [
    { id: "actions", label: "Actions", icon: Route }, { id: "evidence", label: "Evidence", icon: Database },
    { id: "calculation", label: "Calculation", icon: Calculator }, { id: "limits", label: "Limits", icon: ShieldCheck },
  ];
  return (
    <div className="mt-3 overflow-hidden rounded-lg border border-line bg-surface">
      <button type="button" onClick={() => setOpen((current) => !current)} aria-expanded={open} className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left hover:bg-surface-2">
        <span className="flex min-w-0 items-center gap-2">
          <span className="inline-flex size-7 shrink-0 items-center justify-center rounded-md bg-gentian-soft text-gentian"><ShieldCheck className="size-3.5" aria-hidden /></span>
          <span className="min-w-0"><strong className="block text-[12px] text-ink">Show reasoning evidence</strong><span className="block text-[10px] text-ink-3">{evidence.events.length} observed {evidence.events.length === 1 ? "event" : "events"}</span></span>
        </span>
        <ChevronDown className={cn("size-4 shrink-0 text-ink-3 transition-transform", open && "rotate-180")} aria-hidden />
      </button>
      {open ? (
        <div className="border-t border-line p-3">
          <p className="text-[9px] font-semibold uppercase tracking-[0.12em] text-gentian">Assistant Insights · behavioral provenance</p>
          <div className={cn("mt-2 flex items-center gap-2 rounded-md px-2.5 py-2 text-[10.5px] font-medium", unresolved ? "bg-warn-soft text-warn" : "bg-good-soft text-good")}>
            <span className="size-1.5 rounded-full bg-current" />
            {evidence.events.length === 0 ? "Evidence unavailable" : unresolved ? "Partially supported by observed operations" : "Supported by a complete observed trace"}
          </div>
          <div role="tablist" aria-label="Evidence views" className="mt-3 grid grid-cols-4 rounded-md bg-surface-2 p-0.5">
            {tabs.map(({ id, label, icon: Icon }) => (
              <button key={id} role="tab" aria-selected={tab === id} type="button" onClick={() => setTab(id)} className={cn("flex items-center justify-center gap-1 rounded-sm px-1 py-1.5 text-[9.5px] font-medium", tab === id ? "bg-surface text-ink shadow-card" : "text-ink-3 hover:text-ink")}> <Icon className="size-3" aria-hidden />{label}</button>
            ))}
          </div>
          <div role="tabpanel" className="mt-3 min-h-24">
            {tab === "actions" ? <Actions events={evidence.events} /> : null}
            {tab === "evidence" ? <Records records={records} /> : null}
            {tab === "calculation" ? <Calculation event={calculation} /> : null}
            {tab === "limits" ? <Limits hasWrite={hasWrite} incomplete={evidence.incomplete} /> : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
