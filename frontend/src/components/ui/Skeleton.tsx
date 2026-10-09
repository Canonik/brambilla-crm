import { cn } from "@/lib/cn";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-sm bg-surface-3", className)} aria-hidden />;
}

export function SkeletonRows({ rows = 6, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="divide-y divide-line" aria-busy="true" aria-live="polite">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex items-center gap-4 px-3 py-3">
          {Array.from({ length: cols }).map((__, c) => (
            <Skeleton key={c} className={cn("h-3.5", c === 0 ? "w-1/3" : c === cols - 1 ? "ml-auto w-16" : "w-1/6")} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function SkeletonBlock({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={cn("space-y-2", className)} aria-busy="true">
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className={cn("h-3.5", i === lines - 1 ? "w-2/5" : "w-full")} />
      ))}
    </div>
  );
}
