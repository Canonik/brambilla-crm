import { useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { Calculator, ChevronDown, Database, Route, ShieldCheck, SlidersHorizontal } from "lucide-react";
import type { AssistantEvidence } from "@/api/types";
import { cn } from "@/lib/cn";
import { deriveInsights, projectEvidence, type InsightVerdict } from "./evidence";
import { Timeline } from "./insights/Timeline";
import { RecordGraph } from "./insights/RecordGraph";
import { Receipt } from "./insights/Receipt";
import { Limits } from "./insights/Limits";
import { formatMs } from "./insights/status";
import { Grounding } from "./insights/Grounding";
import { Narrative, outcomeSentence } from "./insights/Narrative";
import styles from "./insights/insights.module.css";

type View = "actions" | "evidence" | "calculation" | "limits";

const VIEWS: Array<{ id: View; label: string; icon: typeof Route }> = [
  { id: "actions", label: "Actions", icon: Route },
  { id: "evidence", label: "Evidence", icon: Database },
  { id: "calculation", label: "Calculation", icon: Calculator },
  { id: "limits", label: "Limits", icon: ShieldCheck },
];

const VERDICT: Record<InsightVerdict, { text: string; className: string }> = {
  complete: { text: "Every observed operation settled with a confirmed outcome", className: "bg-good-soft text-good" },
  partial: { text: "Partially supported: at least one step is unresolved or the trace is partial", className: "bg-warn-soft text-warn" },
  none: { text: "No CRM operation was observed for this reply", className: "bg-surface-3 text-ink-2" },
};

export interface EvidenceInspectorProps {
  value: AssistantEvidence;
  className?: string;
}

/**
 * Assistant Insights: the observable execution path behind one reply. Reads
 * the sanitized trace the backend attached, never the reply text, and never
 * anything about the model's internals.
 */
export function EvidenceInspector({ value, className }: EvidenceInspectorProps) {
  const evidence = useMemo(() => projectEvidence(value), [value]);
  const insights = useMemo(() => (evidence ? deriveInsights(evidence) : null), [evidence]);
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<View>("actions");
  const [details, setDetails] = useState(false);
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const id = useId();
  if (!evidence || !insights) return null;

  const onTabKey = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const keys: Record<string, number> = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: VIEWS.length - 1 };
    const next = keys[event.key];
    if (next === undefined) return;
    event.preventDefault();
    const target = (next + VIEWS.length) % VIEWS.length;
    setView(VIEWS[target]!.id);
    tabRefs.current[target]?.focus();
  };

  const counts = [
    `${insights.calls.length} ${insights.calls.length === 1 ? "operation" : "operations"}`,
    insights.records.length ? `${insights.records.length} ${insights.records.length === 1 ? "record" : "records"}` : null,
    insights.writes ? `${insights.committed} of ${insights.writes} ${insights.writes === 1 ? "write" : "writes"} committed` : null,
  ].filter(Boolean).join(" · ");
  const verdict = insights.verdict === "complete" && insights.unsuccessful > 0
    ? { text: `Every operation settled; ${insights.unsuccessful} of ${insights.calls.length} did not succeed and left the CRM unchanged`, className: "bg-warn-soft text-warn" }
    : VERDICT[insights.verdict];
  const panelId = `${id}-panel`;

  return (
    <section className={cn("overflow-hidden rounded-lg border border-line bg-surface text-left", className)} aria-label="Assistant Insights">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        aria-controls={panelId}
        className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left hover:bg-surface-2"
      >
        <span className="flex min-w-0 items-center gap-2.5">
          <span className="inline-flex size-7 shrink-0 items-center justify-center rounded-md bg-gentian-soft text-gentian"><ShieldCheck className="size-3.5" aria-hidden /></span>
          <span className="min-w-0">
            <span className="block text-[12.5px] font-semibold text-ink">Assistant Insights</span>
            <span className="block truncate text-[11px] text-ink-3">{counts}{insights.totalMs ? ` · ${formatMs(insights.totalMs)} in the CRM` : ""}</span>
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-2">
          <span className={cn("size-2 rounded-full", insights.verdict === "complete" && insights.unsuccessful === 0 ? "bg-good" : insights.verdict === "none" ? "bg-line-strong" : "bg-warn")} aria-hidden />
          <ChevronDown className={cn("size-4 text-ink-3 transition-transform", open && "rotate-180")} aria-hidden />
        </span>
      </button>
      <div id={panelId} className={styles.collapse} data-open={open}>
        <div>
          {open ? (
            <div className="border-t border-line p-3">
              <p className="text-[14px] font-semibold leading-6 text-ink">{outcomeSentence(evidence, insights)}</p>
              <Narrative insights={insights} />
              {evidence.grounding ? <Grounding value={evidence.grounding} showDetails={details} /> : null}
              <button
                type="button"
                aria-expanded={details}
                onClick={() => setDetails((current) => !current)}
                className="mt-3 inline-flex min-h-8 items-center gap-1.5 rounded-md border border-line bg-surface px-2.5 text-[12px] font-medium text-ink-2 hover:bg-surface-2"
              >
                <SlidersHorizontal className="size-3.5" aria-hidden />
                Details
              </button>
              <p className={cn("flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[11px] font-medium", verdict.className)} role="status">
                <span className="size-1.5 shrink-0 rounded-full bg-current" aria-hidden />
                {verdict.text}
              </p>
              <div role="tablist" aria-label="Insight views" className="mt-3 grid grid-cols-4 rounded-md bg-surface-2 p-0.5">
                {VIEWS.map(({ id: viewId, label, icon: Icon }, index) => {
                  const active = view === viewId;
                  const badge = viewId === "limits" ? insights.limitations.filter((item) => item.basis === "observed" && item.tone !== "muted").length : viewId === "evidence" ? insights.records.length : viewId === "actions" ? insights.calls.length : insights.calculation ? 1 : 0;
                  return (
                    <button
                      key={viewId}
                      ref={(element) => { tabRefs.current[index] = element; }}
                      id={`${id}-tab-${viewId}`}
                      role="tab"
                      type="button"
                      aria-selected={active}
                      aria-controls={`${id}-view-${viewId}`}
                      tabIndex={active ? 0 : -1}
                      onClick={() => setView(viewId)}
                      onKeyDown={(event) => onTabKey(event, index)}
                      className={cn(
                        "flex items-center justify-center gap-1 rounded-sm px-1 py-1.5 text-[10.5px] font-medium transition-colors",
                        active ? "bg-surface text-ink shadow-card" : "text-ink-3 hover:text-ink",
                      )}
                    >
                      <Icon className="size-3" aria-hidden />
                      {label}
                      {badge ? <span className={cn("tnum rounded-sm px-1 text-[9.5px]", viewId === "limits" ? "bg-warn-soft text-warn" : "bg-surface-3 text-ink-2")}>{badge}</span> : null}
                    </button>
                  );
                })}
              </div>
              <div id={`${id}-view-${view}`} role="tabpanel" aria-labelledby={`${id}-tab-${view}`} tabIndex={0} className="mt-3 min-h-24 focus:outline-none">
                {view === "actions" ? <Timeline calls={insights.calls} showDetails={details} /> : null}
                {view === "evidence" ? <RecordGraph insights={insights} /> : null}
                {view === "calculation" ? <Receipt call={insights.calculation} /> : null}
                {view === "limits" ? <Limits items={insights.limitations} /> : null}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
