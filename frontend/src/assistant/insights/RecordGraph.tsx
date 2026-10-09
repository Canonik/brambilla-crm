import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Pencil } from "lucide-react";
import { cn } from "@/lib/cn";
import type { Insights } from "../evidence";
import { evidenceRecordLink } from "../evidence";
import { NODE_H, NODE_W, layoutGraph } from "./layout";
import { RecordRef, typeLabel } from "./RecordRef";
import styles from "./insights.module.css";

/**
 * Schematic of the records the backend reported for this reply. Nodes are
 * record references; a line exists only where a tool result itself carried
 * the link (an overview, an association read, a write that associated two
 * records). Nothing is inferred from the reply text.
 */
export function RecordGraph({ insights }: { insights: Insights }) {
  const { records, relations } = insights;
  const layout = useMemo(() => layoutGraph(records, relations), [records, relations]);
  const [focus, setFocus] = useState<string | null>(null);
  const navigate = useNavigate();

  if (!records.length) {
    return <p className="text-[12px] text-ink-2">No record reference was included in this reply's trace.</p>;
  }

  const neighbours = new Set<string>();
  if (focus) for (const edge of layout.edges) {
    if (edge.from === focus) neighbours.add(edge.to);
    if (edge.to === focus) neighbours.add(edge.from);
  }

  return (
    <div>
      <div className="overflow-x-auto scroll-quiet rounded-md border border-line bg-surface-2 p-2">
        <svg
          viewBox={`0 0 ${layout.width} ${layout.height}`}
          width="100%"
          style={{ minWidth: Math.min(layout.width, 336), maxWidth: layout.width, height: "auto", display: "block" }}
          role="group"
          aria-label={`${records.length} records and ${layout.edges.length} observed links`}
          fontFamily="inherit"
        >
          <g fill="none" stroke="var(--color-line-strong)" strokeWidth={1.25}>
            {layout.edges.map((edge, index) => {
              const lit = focus === edge.from || focus === edge.to;
              return (
                <path
                  key={`${edge.from}|${edge.to}`}
                  d={edge.path}
                  className={styles.edge}
                  style={{ "--i": index } as React.CSSProperties}
                  stroke={lit ? "var(--color-gentian)" : focus ? "var(--color-line)" : "var(--color-line-strong)"}
                  strokeWidth={lit ? 2 : 1.25}
                />
              );
            })}
          </g>
          {layout.groups.map((group) => (
            <text key={group.type} x={group.x + 2} y={group.y + 14} fontSize={10.5} fill="var(--color-ink-3)" className="font-narrow">
              {group.label} · {group.count}
            </text>
          ))}
          {layout.nodes.map((node, index) => {
            const href = evidenceRecordLink(node.record);
            const dim = focus !== null && focus !== node.key && !neighbours.has(node.key);
            const hub = node.column === "hub";
            return (
              <g
                key={node.key}
                transform={`translate(${node.x},${node.y})`}
                className={cn(styles.fade, href && "cursor-pointer")}
                style={{ "--i": index + 1, opacity: dim ? 0.35 : undefined, transition: "opacity 120ms" } as React.CSSProperties}
                role={href ? "link" : undefined}
                tabIndex={href ? 0 : -1}
                aria-label={`${typeLabel(node.record)} ${node.record.id}${node.record.written ? ", written in this reply" : ""}`}
                onMouseEnter={() => setFocus(node.key)}
                onMouseLeave={() => setFocus(null)}
                onFocus={() => setFocus(node.key)}
                onBlur={() => setFocus(null)}
                onClick={() => href && navigate(href)}
                onKeyDown={(event) => { if (href && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); navigate(href); } }}
              >
                <rect
                  width={NODE_W}
                  height={NODE_H}
                  rx={4}
                  fill={hub ? "var(--color-gentian)" : "var(--color-surface)"}
                  stroke={node.record.written ? "var(--color-signal)" : hub ? "var(--color-gentian-deep)" : focus === node.key ? "var(--color-gentian)" : "var(--color-line-strong)"}
                  strokeWidth={node.record.written || focus === node.key ? 1.75 : 1}
                />
                <text x={10} y={19} fontSize={11} fill={hub ? "var(--color-ink-inverse)" : "var(--color-ink-2)"}>
                  {typeLabel(node.record)}
                </text>
                <text x={NODE_W - 10} y={19} fontSize={11.5} fontWeight={600} textAnchor="end" fill={hub ? "var(--color-ink-inverse)" : "var(--color-ink)"} style={{ fontVariantNumeric: "tabular-nums" }}>
                  #{node.record.id}
                </text>
                {node.record.written ? <circle cx={NODE_W} cy={0} r={4} fill="var(--color-signal)" /> : null}
              </g>
            );
          })}
        </svg>
      </div>
      <p className="mt-1.5 text-[10.5px] text-ink-3">
        A line is drawn only where a tool result itself carried the link. <span className="inline-flex items-center gap-1 align-middle"><span className="inline-block size-2 rounded-full bg-signal" aria-hidden />marks a record written in this reply.</span>
      </p>
      <ul className="mt-3 divide-y divide-line border-t border-line" aria-label="Records referenced by the backend">
        {records.map((record) => (
          <li key={record.key} className="flex items-center justify-between gap-2 py-1.5">
            <RecordRef record={record} />
            <span className="tnum text-[10.5px] text-ink-3">
              {record.written ? <Pencil className="mr-1 inline size-3 text-signal" aria-label="Written" /> : null}
              step {record.steps.join(", ")}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
