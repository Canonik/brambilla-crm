import { describe, expect, it } from "vitest";
import {
  formatDate,
  formatDateTime,
  formatMoney,
  formatNumber,
  formatRelative,
  initials,
  parseHsDate,
  toNumber,
} from "./format";

describe("toNumber", () => {
  it("reads numbers and numeric strings", () => {
    expect(toNumber(12.5)).toBe(12.5);
    expect(toNumber("12.5")).toBe(12.5);
    expect(toNumber("0")).toBe(0);
  });
  it("returns null for empty or invalid values", () => {
    expect(toNumber("")).toBeNull();
    expect(toNumber(null)).toBeNull();
    expect(toNumber(undefined)).toBeNull();
    expect(toNumber("abc")).toBeNull();
  });
});

describe("parseHsDate", () => {
  it("accepts ISO strings", () => {
    expect(parseHsDate("2025-03-12T10:00:00Z")?.toISOString()).toBe("2025-03-12T10:00:00.000Z");
  });
  it("accepts epoch milliseconds as number or string", () => {
    const ms = Date.UTC(2024, 0, 15);
    expect(parseHsDate(ms)?.getTime()).toBe(ms);
    expect(parseHsDate(String(ms))?.getTime()).toBe(ms);
  });
  it("accepts date-only strings", () => {
    expect(parseHsDate("2025-03-12")?.getUTCFullYear()).toBe(2025);
  });
  it("returns null for empty or garbage", () => {
    expect(parseHsDate("")).toBeNull();
    expect(parseHsDate(null)).toBeNull();
    expect(parseHsDate("not a date")).toBeNull();
  });
});

describe("formatMoney", () => {
  it("formats euro with two decimals", () => {
    expect(formatMoney(12345.678)).toBe("€12,345.68");
    expect(formatMoney("1360.36", "EUR")).toBe("€1,360.36");
  });
  it("handles other currencies", () => {
    expect(formatMoney(100, "USD")).toBe("$100.00");
    expect(formatMoney(100, "GBP")).toBe("£100.00");
  });
  it("compacts large values when asked", () => {
    expect(formatMoney(1_250_000, "EUR", { compact: true })).toBe("€1.3M");
    expect(formatMoney(48_210, "EUR", { compact: true })).toBe("€48.2K");
    expect(formatMoney(950, "EUR", { compact: true })).toBe("€950");
  });
  it("returns a dash for missing amounts", () => {
    expect(formatMoney(null)).toBe("–");
    expect(formatMoney("")).toBe("–");
  });
  it("keeps the sign on negative amounts", () => {
    expect(formatMoney(-5131.24)).toBe("-€5,131.24");
  });
});

describe("formatNumber", () => {
  it("groups thousands", () => {
    expect(formatNumber(20497)).toBe("20,497");
    expect(formatNumber(null)).toBe("–");
  });
});

describe("formatDate", () => {
  it("renders a short readable date", () => {
    expect(formatDate("2025-03-12T10:00:00Z")).toBe("12 Mar 2025");
  });
  it("renders a dash for missing dates", () => {
    expect(formatDate(null)).toBe("–");
  });
  it("renders a date and time", () => {
    expect(formatDateTime("2025-03-12T10:05:00Z", "UTC")).toBe("12 Mar 2025, 10:05");
  });
});

describe("formatRelative", () => {
  const now = new Date("2026-12-02T10:00:00Z");
  it("describes the past", () => {
    expect(formatRelative("2026-12-02T09:59:30Z", now)).toBe("just now");
    expect(formatRelative("2026-12-02T08:00:00Z", now)).toBe("2 hours ago");
    expect(formatRelative("2026-11-29T10:00:00Z", now)).toBe("3 days ago");
    expect(formatRelative("2026-09-02T10:00:00Z", now)).toBe("3 months ago");
    expect(formatRelative("2024-12-02T10:00:00Z", now)).toBe("2 years ago");
  });
  it("describes the future", () => {
    expect(formatRelative("2026-12-09T10:00:00Z", now)).toBe("in 7 days");
  });
  it("renders a dash for missing dates", () => {
    expect(formatRelative(null, now)).toBe("–");
  });
});

describe("initials", () => {
  it("takes the first letters of the first two words", () => {
    expect(initials("Nuova Impianti Benedetti S.p.A.")).toBe("NI");
    expect(initials("Elisa")).toBe("E");
    expect(initials("")).toBe("?");
  });
});
