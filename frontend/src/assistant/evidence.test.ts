import { describe, expect, it } from "vitest";
import { evidenceRecordLink, projectEvidence } from "./evidence";

describe("assistant evidence projection", () => {
  it("accepts allowlisted events and drops arbitrary payload fields", () => {
    const value = projectEvidence({
      version: 1,
      incomplete: false,
      events: [{
        sequence: 1, call: 1, tool: "revenue", operation: "read", status: "completed",
        durationMs: 12, inputSummary: "Revenue for company #18 in 2025",
        records: [{ type: "companies", id: "18", name: "SECRET" }, { type: "deals", id: "42" }],
        prompt: "SECRET", result: "SECRET",
        calculation: {
          kind: "sum_money_v1", currency: "EUR", populationComplete: true, populationCount: 1,
          terms: [{ record: { type: "deals", id: "42" }, amount: "125.50", label: "SECRET" }], result: "125.50",
        },
      }],
    });
    expect(value?.events[0]?.label).toBe("Calculated revenue");
    expect(value?.events[0]?.records).toEqual([{ type: "companies", id: "18" }, { type: "deals", id: "42" }]);
    expect(JSON.stringify(value)).not.toContain("SECRET");
    expect(value?.events[0]?.calculation?.result).toBe("125.50");
  });

  it("rejects unknown tools, invalid ids, operation mismatches and non-monotonic events", () => {
    const value = projectEvidence({
      version: 1,
      incomplete: false,
      events: [
        { sequence: 1, call: 1, tool: "search_companies", operation: "read", status: "completed", records: [{ type: "companies", id: "0" }] },
        { sequence: 1, call: 2, tool: "search_companies", operation: "read", status: "completed" },
        { sequence: 2, call: 3, tool: "invented", operation: "read", status: "completed" },
        { sequence: 3, call: 4, tool: "update_record", operation: "read", status: "completed" },
      ],
    });
    expect(value?.events).toHaveLength(1);
    expect(value?.events[0]?.records).toEqual([]);
    expect(value?.incomplete).toBe(true);
  });

  it("fails closed for malformed envelopes and links only supported record pages", () => {
    expect(projectEvidence(null)).toBeNull();
    expect(projectEvidence({ version: 2, events: [], incomplete: false })).toBeNull();
    expect(evidenceRecordLink({ type: "companies", id: "18" })).toBe("/companies/18");
    expect(evidenceRecordLink({ type: "notes", id: "9" })).toBeNull();
  });
});
