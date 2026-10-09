import { Check, CircleAlert, X } from "lucide-react";
import type { EvidenceAutomation, Insights, ProjectedEvidence } from "../evidence";
import { recordKey } from "../evidence";
import { RecordRef } from "./RecordRef";

const SINGULAR = {
  companies: "company", contacts: "contact", deals: "deal", tickets: "ticket",
  products: "product", line_items: "line item", notes: "note", calls: "call",
  emails: "email", meetings: "meeting", tasks: "task",
} as const;

const AUTOMATION_TEXT: Record<EvidenceAutomation["rule"], string> = {
  R10: "opened kickoff ticket",
  R11: "created callback task",
  R12: "linked the company",
};

function plural(value: number, one: string, many = `${one}s`) {
  return `${value} ${value === 1 ? one : many}`;
}

export function outcomeSentence(evidence: ProjectedEvidence, insights: Insights): string {
  const readRecords = new Set(
    insights.calls.filter((call) => call.operation === "read").flatMap((call) => call.records.map(recordKey)),
  ).size;
  const committed = insights.calls.filter((call) => call.status === "committed");
  const changedTypes = new Set(committed.flatMap((call) => call.decisionPath?.chosen?.type ? [call.decisionPath.chosen.type] : []));
  const changedLabel = committed.length === 1 && changedTypes.size === 1
    ? plural(1, SINGULAR[[...changedTypes][0] as keyof typeof SINGULAR])
    : plural(committed.length, "record");
  const automations = committed.reduce((sum, call) => sum + (call.decisionPath?.automations.length ?? 0), 0);
  const grounding = evidence.grounding ?? { facts: [], grounded: 0, unverified: 0 };
  return `Read ${plural(readRecords, "record")}, changed ${changedLabel}, triggered ${plural(automations, "automation")}, ${grounding.grounded} of ${grounding.facts.length} facts found in CRM data.`;
}

export function Narrative({ insights }: { insights: Insights }) {
  const steps: React.ReactNode[] = [];
  for (const call of insights.calls) {
    if (call.operation === "read") {
      const found = call.count ?? call.records.length;
      steps.push(<span>{call.label}: {plural(found, "record")} found.</span>);
      continue;
    }
    const path = call.decisionPath;
    if (path?.chosen) {
      steps.push(<span className="inline-flex flex-wrap items-center gap-1.5">Chose <RecordRef record={path.chosen} className="h-7 text-[12.5px]" />.</span>);
    }
    const saved = call.status === "committed";
    const unknown = call.status === "unknown" || !call.settled;
    steps.push(
      <span className="inline-flex flex-wrap items-center gap-1.5">
        {saved ? <Check className="size-4 shrink-0 text-good" aria-label="Saved" /> : unknown ? <CircleAlert className="size-4 shrink-0 text-warn" aria-label="Not verified" /> : <X className="size-4 shrink-0 text-bad" aria-label="Not saved" />}
        {path?.action ?? call.label}: <strong className={saved ? "text-good" : unknown ? "text-warn" : "text-bad"}>{saved ? "saved" : unknown ? "not verified" : "not saved"}</strong>.
      </span>,
    );
    for (const automation of path?.automations ?? []) {
      steps.push(
        <span className="inline-flex flex-wrap items-center gap-1.5">
          Rule {automation.rule} {AUTOMATION_TEXT[automation.rule]} <RecordRef record={automation.record} className="h-7 text-[12.5px]" />.
        </span>,
      );
    }
  }
  if (!steps.length) steps.push(<span>Answered without reading or changing CRM records.</span>);
  return (
    <ol className="mt-3 list-decimal space-y-2.5 pl-6 text-[13.5px] leading-6 text-ink" aria-label="What the assistant did in plain words">
      {steps.map((step, index) => <li key={index} className="pl-1.5">{step}</li>)}
    </ol>
  );
}
