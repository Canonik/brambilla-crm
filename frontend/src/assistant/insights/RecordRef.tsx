import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import type { EvidenceRecord } from "@/api/types";
import { cn } from "@/lib/cn";
import { evidenceRecordLink } from "../evidence";
import { TYPE_LABELS } from "./layout";

export function typeLabel(record: EvidenceRecord): string {
  return TYPE_LABELS[record.type] ?? record.type;
}

/** A record reference as the backend reported it: type and id, linked when the CRM has a page for it. */
type NamedRecord = EvidenceRecord & { label?: string; detail?: string };

export function RecordRef({ record, className, muted }: { record: NamedRecord; className?: string; muted?: boolean }) {
  const href = evidenceRecordLink(record);
  const body = (
    <>
      {record.label ? (
        <>
          <span className="font-semibold text-ink">{record.label}</span>
          {record.detail ? <span className="text-ink-3">({record.detail})</span> : null}
          <span className="tnum text-[10px] text-ink-3">#{record.id}</span>
        </>
      ) : (
        <>
          <span className={cn("font-narrow", muted ? "text-ink-3" : "text-ink-2")}>{typeLabel(record)}</span>
          <span className="tnum font-semibold text-ink">#{record.id}</span>
        </>
      )}
      {href ? <ArrowUpRight className="size-3 text-ink-3" aria-hidden /> : null}
    </>
  );
  const classes = cn(
    "inline-flex h-6 items-center gap-1 rounded-sm border border-line bg-surface px-1.5 text-[11.5px] leading-none",
    href && "hover:border-gentian-line hover:bg-gentian-soft/60",
    className,
  );
  return href ? (
    <Link to={href} className={classes} aria-label={record.label ? `Open ${record.label}, ${typeLabel(record)} ${record.id}` : `Open ${typeLabel(record)} ${record.id}`}>{body}</Link>
  ) : (
    <span className={classes}>{body}</span>
  );
}
