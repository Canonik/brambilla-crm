// Formatting helpers. HubSpot-shaped APIs return every property as a string,
// dates as ISO or epoch milliseconds, and numbers as strings or numbers. These
// helpers normalise that into something the UI can render.

export const DASH = "–";

export function toNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string") {
    const n = Number(value.trim());
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

export function parseHsDate(value: unknown): Date | null {
  if (value === null || value === undefined || value === "") return null;
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
  if (typeof value === "number") {
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (/^-?\d{10,}$/.test(trimmed)) {
      const d = new Date(Number(trimmed));
      return Number.isNaN(d.getTime()) ? null : d;
    }
    const d = new Date(trimmed);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  return null;
}

const currencyFormatters = new Map<string, Intl.NumberFormat>();

function currencyFormatter(currency: string, compact: boolean) {
  const key = `${currency}:${compact}`;
  let f = currencyFormatters.get(key);
  if (!f) {
    f = new Intl.NumberFormat("en-IE", {
      style: "currency",
      currency,
      currencyDisplay: "narrowSymbol",
      ...(compact
        ? { notation: "compact", maximumFractionDigits: 1 }
        : { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
    });
    currencyFormatters.set(key, f);
  }
  return f;
}

export function formatMoney(
  amount: unknown,
  currency: string | null | undefined = "EUR",
  opts: { compact?: boolean } = {},
): string {
  const n = toNumber(amount);
  if (n === null) return DASH;
  const code = (currency || "EUR").toUpperCase();
  try {
    return currencyFormatter(code, Boolean(opts.compact)).format(n);
  } catch {
    return `${n.toFixed(2)} ${code}`;
  }
}

const numberFormatter = new Intl.NumberFormat("en-IE", { maximumFractionDigits: 2 });

export function formatNumber(value: unknown): string {
  const n = toNumber(value);
  return n === null ? DASH : numberFormatter.format(n);
}

export function formatPercent(value: unknown): string {
  const n = toNumber(value);
  return n === null ? DASH : `${numberFormatter.format(n)}%`;
}

const dateFormatter = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

export function formatDate(value: unknown): string {
  const d = parseHsDate(value);
  return d ? dateFormatter.format(d) : DASH;
}

export function formatDateTime(value: unknown, timeZone?: string): string {
  const d = parseHsDate(value);
  if (!d) return DASH;
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    ...(timeZone ? { timeZone } : {}),
  }).format(d);
}

export function formatRelative(value: unknown, now: Date = new Date()): string {
  const d = parseHsDate(value);
  if (!d) return DASH;
  const diffMs = d.getTime() - now.getTime();
  const abs = Math.abs(diffMs);
  const sec = Math.round(abs / 1000);
  if (sec < 60) return "just now";
  const units: Array<[string, number]> = [
    ["year", 365 * 24 * 3600],
    ["month", 30 * 24 * 3600],
    ["day", 24 * 3600],
    ["hour", 3600],
    ["minute", 60],
  ];
  for (const [name, size] of units) {
    if (sec >= size) {
      const count = Math.floor(sec / size);
      const label = `${count} ${name}${count === 1 ? "" : "s"}`;
      return diffMs < 0 ? `${label} ago` : `in ${label}`;
    }
  }
  return "just now";
}

export function initials(name: string | null | undefined): string {
  const words = (name ?? "").trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  return words
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("");
}

export function fullName(first?: string | null, last?: string | null, fallback = "Unnamed contact") {
  const name = [first, last].filter(Boolean).join(" ").trim();
  return name || fallback;
}

export function userLabel(email: string | null | undefined): string {
  if (!email) return "Unassigned";
  const local = email.split("@")[0] ?? email;
  return local
    .split(/[._-]+/)
    .filter(Boolean)
    .map((p) => p[0]!.toUpperCase() + p.slice(1))
    .join(" ");
}

export function domainOf(value: string | null | undefined): string | null {
  if (!value) return null;
  return value.replace(/^https?:\/\//i, "").replace(/^www\./i, "").replace(/\/.*$/, "") || null;
}

export function truncate(text: string, max = 120) {
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1).trimEnd()}…`;
}
