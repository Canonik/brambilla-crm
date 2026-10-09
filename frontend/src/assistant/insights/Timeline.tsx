import { useState } from "react";
import { Check, ChevronRight, CircleAlert, CircleDashed, Pencil, Search, X } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { cn } from "@/lib/cn";
import type { InsightCall } from "../evidence";
import { FAILURE_LABELS } from "../evidence";
import { RecordRef } from "./RecordRef";
import { STATUS_LABELS, STATUS_TONES, formatMs } from "./status";
import { DecisionPath } from "./DecisionPath";
import styles from "./insights.module.css";

const WRITE_STAGES: Array<{ key: "attempted" | "awaiting_commit" | "committed"; label: string }> = [
  { key: "attempted", label: "Requested" },
  { key: "awaiting_commit", label: "Store returned" },
  { key: "committed", label: "Commit confirmed" },
];

function Glyph({ call }: { call: InsightCall }) {
  const base = "inline-flex size-5 items-center justify-center rounded-full ring-4 ring-surface";
  if (call.status === "completed" || call.status === "committed") return <span className={cn(base, "bg-good text-white")}><Check className="size-3" aria-hidden /></span>;
  if (call.status === "failed" || call.status === "rolled_back") return <span className={cn(base, "bg-bad text-white")}><X className="size-3" aria-hidden /></span>;
  if (call.status === "unknown") return <span className={cn(base, "bg-warn text-white")}><CircleAlert className="size-3" aria-hidden /></span>;
  return <span className={cn(base, "bg-surface-3 text-ink-3")}><CircleDashed className="size-3" aria-hidden /></span>;
}

/** Write calls show the three observed checkpoints so a returned tool is never mistaken for a committed one. */
function WriteStages({ call }: { call: InsightCall }) {
  const reached = new Set(call.history);
  const broken = call.status === "rolled_back" || call.status === "unknown";
  return (
    <ol className="mt-2 flex flex-wrap items-center gap-x-1 gap-y-1 text-[10.5px]" aria-label="Write checkpoints">
      {WRITE_STAGES.map((stage, index) => {
        const hit = reached.has(stage.key);
        const last = index === WRITE_STAGES.length - 1;
        return (
          <li key={stage.key} className="flex items-center gap-1">
            <span className={cn("inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5", hit ? "bg-good-soft text-good" : broken && last ? "bg-bad-soft text-bad line-through" : "bg-surface-3 text-ink-3")}>
              {hit ? <Check className="size-2.5" aria-hidden /> : null}
              {stage.label}
            </span>
            {!last ? <ChevronRight className="size-3 text-ink-3" aria-hidden /> : null}
          </li>
        );
      })}
      {broken ? (
        <li className={cn("inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5", call.status === "unknown" ? "bg-warn-soft text-warn" : "bg-bad-soft text-bad")}>
          {STATUS_LABELS[call.status]}
        </li>
      ) : null}
    </ol>
  );
}

function Row({ call, index, showDetails }: { call: InsightCall; index: number; showDetails: boolean }) {
  const [open, setOpen] = useState(false);
  const detailId = `insight-call-${call.call}-detail`;
  const hasDetail = call.records.length > 0 || call.failure !== undefined;
  const summary = [
    call.inputSummary,
    call.count !== undefined ? (call.total !== undefined && call.total > call.count ? `${call.count} of ${call.total} rows` : `${call.count} ${call.count === 1 ? "row" : "rows"}`) : null,
    call.records.length ? `${call.records.length} ${call.records.length === 1 ? "record" : "records"}` : null,
  ].filter(Boolean).join(" · ");
  return (
    <li className={cn("relative pb-4 pl-7 last:pb-0", styles.reveal)} style={{ "--i": index } as React.CSSProperties}>
      <span className="absolute left-0 top-0.5"><Glyph call={call} /></span>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 text-[12.5px] font-semibold text-ink">
            <span className="tnum text-ink-3">{call.step}.</span>
            {call.operation === "write" ? <Pencil className="size-3 text-signal" aria-hidden /> : <Search className="size-3 text-gentian" aria-hidden />}
            {call.label}
          </p>
          {summary ? <p className="mt-0.5 text-[11.5px] text-ink-2">{summary}</p> : null}
        </div>
        {showDetails ? <div className="flex shrink-0 flex-col items-end gap-1">
          <Badge tone={STATUS_TONES[call.status]} size="sm" dot>{STATUS_LABELS[call.status]}</Badge>
          {call.durationMs !== undefined ? <span className="tnum text-[10.5px] text-ink-3">{formatMs(call.durationMs)}</span> : null}
        </div> : null}
      </div>
      {call.operation === "write" ? <WriteStages call={call} /> : null}
      {showDetails && call.decisionPath ? <DecisionPath path={call.decisionPath} call={call} /> : null}
      {call.failure ? <p className="mt-1.5 text-[11.5px] text-bad">This step {FAILURE_LABELS[call.failure]}.</p> : null}
      {showDetails && hasDetail && call.records.length ? (
        <>
          <button
            type="button"
            aria-expanded={open}
            aria-controls={detailId}
            onClick={() => setOpen((value) => !value)}
            className="mt-1.5 inline-flex items-center gap-1 text-[11.5px] font-medium text-gentian hover:underline"
          >
            <ChevronRight className={cn("size-3 transition-transform", open && "rotate-90")} aria-hidden />
            {open ? "Hide records" : `Records this step referenced (${call.records.length})`}
          </button>
          <div id={detailId} className={styles.collapse} data-open={open}>
            <div>
              <ul className="mt-2 flex flex-wrap gap-1.5">
                {call.records.map((record) => <li key={`${record.type}:${record.id}`}><RecordRef record={record} /></li>)}
              </ul>
            </div>
          </div>
        </>
      ) : null}
    </li>
  );
}

export function Timeline({ calls, showDetails = false }: { calls: InsightCall[]; showDetails?: boolean }) {
  if (!calls.length) {
    return <p className="text-[12px] text-ink-2">No CRM operation was observed for this reply.</p>;
  }
  return (
    <ol className="relative ml-2.5 border-l border-line pl-0 [&>li]:-ml-2.5" aria-label="Observed operations in order">
      {calls.map((call, index) => <Row key={call.call} call={call} index={index} showDetails={showDetails} />)}
    </ol>
  );
}
