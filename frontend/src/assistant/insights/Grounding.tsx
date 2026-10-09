import { AlertTriangle, Check } from "lucide-react";
import { cn } from "@/lib/cn";
import type { EvidenceGrounding, GroundingKind } from "../evidence";

const LABELS: Record<GroundingKind, string> = {
  amount: "Amount",
  record_id: "Record ID",
  email: "Email",
  date: "Date",
  name: "Record name",
};

export function Grounding({ value, showDetails = false }: { value: EvidenceGrounding; showDetails?: boolean }) {
  return (
    <section className="mt-3 rounded-md border border-line bg-surface-2 p-2.5" aria-labelledby="grounding-title">
      <div className="flex items-center justify-between gap-3">
        <h3 id="grounding-title" className="text-[11.5px] font-semibold text-ink">
          Grounded facts {value.grounded} of {value.facts.length}
        </h3>
        {value.unverified ? (
          <span className="inline-flex items-center gap-1 text-[10.5px] font-medium text-warn">
            <AlertTriangle className="size-3" aria-hidden />
            {value.unverified} unverified
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 text-[10.5px] font-medium text-good">
            <Check className="size-3" aria-hidden />
            All matched
          </span>
        )}
      </div>
      {value.facts.length ? (
        <ul className="mt-2 grid gap-1" aria-label="Facts checked against this turn's CRM tool outputs">
          {value.facts.map((fact, index) => (
            <li
              key={`${fact.kind}:${fact.text}:${index}`}
              className={cn(
                "flex min-w-0 items-center justify-between gap-2 rounded-sm border px-2 py-1 text-[11px]",
                fact.status === "grounded" ? "border-good/20 bg-good-soft text-ink" : "border-warn/30 bg-warn-soft text-warn",
              )}
            >
              <span className="min-w-0 truncate"><span className="text-[9.5px] font-semibold uppercase tracking-wide opacity-70">{LABELS[fact.kind]}</span> · {fact.text}</span>
              <span className="shrink-0 font-medium">
                {fact.status === "grounded" ? (showDetails ? `Event ${fact.event}` : "Found in CRM") : "Unverified"}
              </span>
            </li>
          ))}
        </ul>
      ) : <p className="mt-1.5 text-[11px] text-ink-3">No candidate facts were found in this reply.</p>}
    </section>
  );
}
