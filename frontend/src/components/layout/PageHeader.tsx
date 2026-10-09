import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/cn";

export function PageHeader({
  title,
  eyebrow,
  crumbs,
  meta,
  actions,
  leading,
  className,
  children,
}: {
  title: ReactNode;
  eyebrow?: ReactNode;
  crumbs?: Array<{ label: string; to?: string }>;
  meta?: ReactNode;
  actions?: ReactNode;
  leading?: ReactNode;
  className?: string;
  children?: ReactNode;
}) {
  return (
    <header className={cn("border-b border-line bg-surface px-6 pt-4 pb-0", className)}>
      {crumbs?.length ? (
        <nav aria-label="Breadcrumb" className="mb-2 flex items-center gap-1 text-[12px] text-ink-3">
          {crumbs.map((c, i) => (
            <span key={`${c.label}-${i}`} className="inline-flex items-center gap-1">
              {c.to ? (
                <Link to={c.to} className="hover:text-ink">
                  {c.label}
                </Link>
              ) : (
                <span className="text-ink-2">{c.label}</span>
              )}
              {i < crumbs.length - 1 ? <ChevronRight className="size-3" aria-hidden /> : null}
            </span>
          ))}
        </nav>
      ) : null}
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3 pb-4">
        <div className="flex min-w-0 items-center gap-3">
          {leading}
          <div className="min-w-0">
            {eyebrow ? <div className="mb-0.5 text-[12px] text-ink-2">{eyebrow}</div> : null}
            <h1 className="truncate font-wide text-[22px] font-semibold tracking-tight text-ink">{title}</h1>
            {meta ? <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-ink-2">{meta}</div> : null}
          </div>
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </header>
  );
}
