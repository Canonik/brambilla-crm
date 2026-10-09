import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

export function Card({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-lg border border-line bg-surface", className)} {...rest} />;
}

export function CardHeader({
  title,
  meta,
  actions,
  className,
}: {
  title: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex min-h-11 items-center justify-between gap-3 border-b border-line px-4 py-2", className)}>
      <div className="flex min-w-0 items-baseline gap-2">
        <h2 className="truncate text-[13.5px] font-semibold text-ink">{title}</h2>
        {meta ? <span className="text-[12px] text-ink-3 tnum">{meta}</span> : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-1.5">{actions}</div> : null}
    </div>
  );
}

export function CardBody({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-4", className)} {...rest} />;
}
