import { cn } from "@/lib/cn";
import { formatMoney } from "@/lib/format";

// Where a customer sits on Brambilla's class scale (R8): C above zero,
// B from 20,000, A from 100,000 euro of revenue won in 2025.
const B_FROM = 20_000;
const A_FROM = 100_000;
const A_FULL = 300_000;

function position(revenue: number): number {
  if (revenue <= 0) return 0;
  if (revenue < B_FROM) return (revenue / B_FROM) * (1 / 3);
  if (revenue < A_FROM) return 1 / 3 + ((revenue - B_FROM) / (A_FROM - B_FROM)) * (1 / 3);
  return 2 / 3 + Math.min(1, (revenue - A_FROM) / (A_FULL - A_FROM)) * (1 / 3);
}

export function ClassScale({ revenue, className }: { revenue: number; className?: string }) {
  const pos = position(revenue);
  const cls = revenue >= A_FROM ? "A" : revenue >= B_FROM ? "B" : revenue > 0 ? "C" : "";
  return (
    <div className={cn("select-none", className)} aria-label={`Revenue ${formatMoney(revenue)} places this customer in class ${cls || "none"}`}>
      <div className="relative h-2 w-full overflow-visible rounded-full bg-surface-3">
        <div className="absolute inset-y-0 left-0 w-1/3 rounded-l-full bg-line-strong/60" />
        <div className="absolute inset-y-0 left-1/3 w-1/3 bg-gentian-line" />
        <div className="absolute inset-y-0 left-2/3 w-1/3 rounded-r-full bg-signal/35" />
        {revenue > 0 ? (
          <div
            className={cn(
              "absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface shadow-[0_0_0_1px_rgba(28,33,40,0.25)]",
              cls === "A" ? "bg-signal" : cls === "B" ? "bg-gentian" : "bg-ink-2",
            )}
            style={{ left: `${pos * 100}%` }}
          />
        ) : null}
      </div>
      <div className="relative mt-1.5 h-4 text-[11px] text-ink-3 tnum">
        <span className="absolute left-0">0</span>
        <span className="absolute left-1/3 -translate-x-1/2">{formatMoney(B_FROM, "EUR", { compact: true })}</span>
        <span className="absolute left-2/3 -translate-x-1/2">{formatMoney(A_FROM, "EUR", { compact: true })}</span>
        <span className="absolute right-0 text-ink-3">Class A</span>
      </div>
    </div>
  );
}
