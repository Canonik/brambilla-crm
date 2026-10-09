import { toNumber } from "./format";

// Fixed rates from Brambilla's management control (R8). Used only to show
// pipeline totals in one currency; the records keep their own currency.
export const FX_TO_EUR: Record<string, number> = { EUR: 1, USD: 0.92, GBP: 1.17 };

export function toEur(amount: unknown, currency: string | null | undefined): number | null {
  const n = toNumber(amount);
  if (n === null) return null;
  const rate = FX_TO_EUR[(currency || "EUR").toUpperCase()] ?? 1;
  return n * rate;
}

export function sumEur(items: Array<{ amount: unknown; currency: string | null | undefined }>): { total: number; counted: number; skipped: number } {
  let total = 0;
  let counted = 0;
  let skipped = 0;
  for (const it of items) {
    const v = toEur(it.amount, it.currency);
    if (v === null) skipped++;
    else {
      total += v;
      counted++;
    }
  }
  return { total: Math.round(total * 100) / 100, counted, skipped };
}
