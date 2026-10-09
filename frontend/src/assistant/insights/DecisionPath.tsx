import { ChevronRight } from "lucide-react";
import type { EvidenceDecisionPath, InsightCall } from "../evidence";
import { RecordRef } from "./RecordRef";

const RULE_LABELS = {
  R10: "kickoff ticket",
  R11: "callback task",
  R12: "company association",
} as const;

function Step({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <li className="flex min-w-0 items-center gap-1">
      <span className="min-w-0 rounded-sm border border-line bg-surface-2 px-1.5 py-1">
        <span className="block text-[9px] font-semibold uppercase tracking-wide text-ink-3">{label}</span>
        <span className="block truncate text-[10.5px] font-medium text-ink-2">{children}</span>
      </span>
      <ChevronRight className="size-3 shrink-0 text-ink-3 last:hidden" aria-hidden />
    </li>
  );
}

export function DecisionPath({ path, call }: { path: EvidenceDecisionPath; call: InsightCall }) {
  return (
    <div className="mt-2 rounded-md border border-line bg-surface px-2 py-2">
      <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-ink-3">Decision path</p>
      <ol className="flex flex-wrap items-stretch gap-1" aria-label={`Decision path for write step ${call.step}`}>
        <Step label="Question">Your request</Step>
        <Step label="Searches">
          {path.searches.length ? `Events ${path.searches.join(", ")} · ${path.candidates} ${path.candidates === 1 ? "candidate" : "candidates"}` : "No preceding CRM read"}
        </Step>
        <Step label="Chosen">
          {path.chosen ? <RecordRef record={path.chosen} /> : "No record returned"}
        </Step>
        <Step label="Write">{call.label}</Step>
        <Step label="Automation">
          {path.automations.length ? (
            <span className="flex flex-wrap gap-x-1.5 gap-y-1">
              {path.automations.map((automation) => (
                <span key={`${automation.rule}:${automation.record.type}:${automation.record.id}`} className="inline-flex items-center gap-1">
                  {automation.rule} {RULE_LABELS[automation.rule]} <RecordRef record={automation.record} />
                </span>
              ))}
            </span>
          ) : "None reported by the CRM"}
        </Step>
      </ol>
    </div>
  );
}
