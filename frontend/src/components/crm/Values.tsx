import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { cn } from "@/lib/cn";
import { DASH, formatDate, formatDateTime, formatMoney, formatRelative, parseHsDate } from "@/lib/format";
import { userName } from "@/api/users";
import { Avatar } from "@/components/ui/Avatar";

export function Money({
  amount,
  currency,
  compact,
  className,
  muted,
}: {
  amount: unknown;
  currency?: string | null;
  compact?: boolean;
  className?: string;
  muted?: boolean;
}) {
  const text = formatMoney(amount, currency, { compact });
  const isDash = text === DASH;
  return (
    <span className={cn("tnum", (isDash || muted) && "text-ink-3", className)} title={isDash ? "No amount" : formatMoney(amount, currency)}>
      {text}
    </span>
  );
}

export function DateText({ value, className, withTime }: { value: unknown; className?: string; withTime?: boolean }) {
  const d = parseHsDate(value);
  if (!d) return <span className={cn("text-ink-3", className)}>{DASH}</span>;
  return (
    <time dateTime={d.toISOString()} title={formatDateTime(d)} className={cn("tnum whitespace-nowrap", className)}>
      {withTime ? formatDateTime(d) : formatDate(d)}
    </time>
  );
}

/**
 * "3 days ago" for past instants. Dates in the future (the export runs past
 * today's clock) are shown as plain dates unless `allowFuture` is set.
 */
export function RelativeTime({ value, className, allowFuture }: { value: unknown; className?: string; allowFuture?: boolean }) {
  const d = parseHsDate(value);
  if (!d) return <span className={cn("text-ink-3", className)}>{DASH}</span>;
  const future = d.getTime() > Date.now() + 60_000;
  return (
    <time dateTime={d.toISOString()} title={formatDateTime(d)} className={cn("whitespace-nowrap tnum", className)}>
      {future && !allowFuture ? formatDate(d) : formatRelative(d)}
    </time>
  );
}

export function OwnerChip({ email, size = "sm", className, fallback = "Unassigned" }: { email: string | null | undefined; size?: "xs" | "sm"; className?: string; fallback?: string }) {
  const name = userName(email, fallback);
  if (!email) return <span className={cn("text-ink-3", className)}>{fallback}</span>;
  return (
    <span className={cn("inline-flex min-w-0 items-center gap-1.5", className)} title={email}>
      <Avatar name={name} size={size} />
      <span className="truncate">{name}</span>
    </span>
  );
}

export function RecordLink({ to, children, className, stop = true }: { to: string; children: ReactNode; className?: string; stop?: boolean }) {
  return (
    <Link
      to={to}
      onClick={stop ? (e) => e.stopPropagation() : undefined}
      className={cn("font-medium text-ink hover:text-gentian hover:underline underline-offset-2 decoration-gentian/40", className)}
    >
      {children}
    </Link>
  );
}

export function Empty({ children = "–" }: { children?: ReactNode }) {
  return <span className="text-ink-3">{children}</span>;
}

export function PropertyList({ items, className, columns = 1 }: { items: Array<{ label: string; value: ReactNode }>; className?: string; columns?: 1 | 2 }) {
  return (
    <dl className={cn("grid gap-x-6 gap-y-2.5 text-[13px]", columns === 2 ? "grid-cols-2" : "grid-cols-1", className)}>
      {items.map((it) => (
        <div key={it.label} className="grid grid-cols-[112px_1fr] items-baseline gap-2">
          <dt className="truncate text-ink-3">{it.label}</dt>
          <dd className="min-w-0 break-words text-ink">{it.value ?? <Empty />}</dd>
        </div>
      ))}
    </dl>
  );
}
