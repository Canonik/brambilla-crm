import { Check, CircleAlert } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import type { InsightCall } from "../evidence";
import { RecordRef } from "./RecordRef";

function cents(value: string): bigint {
  const negative = value.startsWith("-");
  const digits = (negative ? value.slice(1) : value).replace(".", "");
  const amount = BigInt(digits);
  return negative ? -amount : amount;
}

function money(value: string): string {
  const amount = Number(value);
  return Number.isFinite(amount)
    ? new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(amount)
    : `${value} EUR`;
}

const POLICIES: Record<string, string> = {
  brambilla_revenue_v1: "Brambilla revenue rule (R8): deals won or renewed with a close date in the year, credit notes subtracted, USD × 0.92, GBP × 1.17, half-up to the cent.",
};

/** The deterministic sum the backend computed, re-added here in integer cents so the two can be compared. */
export function Receipt({ call }: { call?: InsightCall }) {
  const calculation = call?.calculation;
  if (!call || !calculation) {
    return <p className="text-[12px] text-ink-2">This reply did not involve a deterministic calculation, so there is no receipt to show.</p>;
  }
  const computed = calculation.terms.reduce((sum, term) => sum + cents(term.amount), 0n);
  const matches = computed === cents(calculation.result);
  const complete = calculation.populationComplete && calculation.populationCount === calculation.terms.length;
  const ok = complete && matches;
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[12.5px] font-semibold text-ink">
          {call.label}{calculation.year ? ` · ${calculation.year}` : ""}
        </p>
        <Badge tone={ok ? "good" : "warn"} size="sm" icon={ok ? <Check className="size-3" aria-hidden /> : <CircleAlert className="size-3" aria-hidden />}>
          {!complete ? "Inputs partially shown" : matches ? "Re-added in the browser: matches" : "Re-added in the browser: differs"}
        </Badge>
      </div>
      {calculation.policy && POLICIES[calculation.policy] ? <p className="mt-1 text-[11.5px] text-ink-2">{POLICIES[calculation.policy]}</p> : null}
      <table className="mt-3 w-full text-[12px]">
        <thead>
          <tr className="text-left text-[10.5px] text-ink-3">
            <th scope="col" className="pb-1 font-medium">Input</th>
            <th scope="col" className="pb-1 text-right font-medium">Amount in EUR</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line border-y border-line">
          {calculation.terms.map((term) => (
            <tr key={`${term.record.type}:${term.record.id}`}>
              <td className="py-1.5"><RecordRef record={term.record} /></td>
              <td className="tnum py-1.5 text-right text-ink">{money(term.amount)}</td>
            </tr>
          ))}
          {calculation.terms.length === 0 ? (
            <tr><td colSpan={2} className="py-2 text-ink-2">No deal matched the rule, so the sum is zero.</td></tr>
          ) : null}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row" className="pt-2 text-left text-[12px] font-semibold text-ink">
              Sum of {calculation.populationCount} {calculation.populationCount === 1 ? "deal" : "deals"}
              {!complete ? <span className="ml-1 font-normal text-warn">({calculation.terms.length} shown)</span> : null}
            </th>
            <td className="tnum pt-2 text-right text-[13px] font-semibold text-ink">{money(calculation.result)}</td>
          </tr>
        </tfoot>
      </table>
      <p className="mt-2 text-[10.5px] text-ink-3">Inputs and result are the values the backend computed from the stored deals. The browser only re-adds them.</p>
    </div>
  );
}
