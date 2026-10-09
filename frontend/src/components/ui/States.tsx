import type { ReactNode } from "react";
import { RefreshCw, TriangleAlert } from "lucide-react";
import { Button } from "./Button";
import { cn } from "@/lib/cn";
import { ApiError } from "@/api/client";

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
  compact,
}: {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
  compact?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center",
        compact ? "gap-1.5 px-4 py-8" : "gap-2 px-6 py-16",
        className,
      )}
    >
      {icon ? <div className="mb-1 text-ink-3 [&>svg]:size-6">{icon}</div> : null}
      <p className="text-[14px] font-semibold text-ink">{title}</p>
      {description ? <p className="max-w-sm text-[13px] text-ink-2">{description}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message || "Something went wrong.";
  return "Something went wrong.";
}

export function ErrorState({
  error,
  onRetry,
  title = "Could not load this",
  className,
  compact,
}: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
  className?: string;
  compact?: boolean;
}) {
  const status = error instanceof ApiError ? error.status : undefined;
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center gap-2 text-center",
        compact ? "px-4 py-8" : "px-6 py-16",
        className,
      )}
    >
      <TriangleAlert className="size-6 text-bad" aria-hidden />
      <p className="text-[14px] font-semibold text-ink">{title}</p>
      <p className="max-w-md text-[13px] text-ink-2">
        {errorMessage(error)}
        {status ? <span className="ml-1 text-ink-3 tnum">({status})</span> : null}
      </p>
      {onRetry ? (
        <Button variant="secondary" size="sm" icon={<RefreshCw className="size-3.5" />} onClick={onRetry} className="mt-1">
          Try again
        </Button>
      ) : null}
    </div>
  );
}

export function InlineError({ error, className }: { error: unknown; className?: string }) {
  return (
    <p role="alert" className={cn("flex items-start gap-2 rounded-md border border-bad/30 bg-bad-soft px-3 py-2 text-[13px] text-bad", className)}>
      <TriangleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden />
      <span>{errorMessage(error)}</span>
    </p>
  );
}
