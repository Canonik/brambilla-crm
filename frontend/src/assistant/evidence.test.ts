import { describe, expect, it } from "vitest";
import { deriveInsights, evidenceRecordLink, projectEvidence } from "./evidence";

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

  it("accepts the attachment, legacy id and line item tools", () => {
    const value = projectEvidence({
      version: 1, incomplete: false,
      events: [
        { sequence: 1, call: 1, tool: "preview_attachment", operation: "read", status: "completed" },
        { sequence: 2, call: 2, tool: "import_attachment", operation: "write", status: "committed", records: [{ type: "contacts", id: "801" }] },
        { sequence: 3, call: 3, tool: "list_deal_line_items", operation: "read", status: "completed", records: [{ type: "deals", id: "42" }, { type: "line_items", id: "700" }], relations: [{ from: { type: "deals", id: "42" }, to: { type: "line_items", id: "700" } }] },
      ],
    });
    expect(value?.incomplete).toBe(false);
    expect(value?.events.map((event) => event.label)).toEqual(["Previewed a CSV attachment", "Imported a CSV attachment", "Retrieved deal line items"]);
  });

  it("fails closed for malformed envelopes and links only supported record pages", () => {
    expect(projectEvidence(null)).toBeNull();
    expect(projectEvidence({ version: 2, events: [], incomplete: false })).toBeNull();
    expect(evidenceRecordLink({ type: "companies", id: "18" })).toBe("/companies/18");
    expect(evidenceRecordLink({ type: "notes", id: "9" })).toBeNull();
  });
});

describe("assistant insights derivation", () => {
  const trace = {
    version: 1,
    incomplete: false,
    events: [
      { sequence: 1, call: 1, tool: "search_companies", operation: "read", status: "attempted" },
      { sequence: 2, call: 1, tool: "search_companies", operation: "read", status: "completed", durationMs: 9, count: 1, total: 1, records: [{ type: "companies", id: "18" }] },
      { sequence: 3, call: 2, tool: "company_overview", operation: "read", status: "completed", durationMs: 30, inputSummary: "Company #18",
        records: [{ type: "companies", id: "18" }, { type: "contacts", id: "77" }, { type: "deals", id: "42" }],
        relations: [
          { from: { type: "companies", id: "18" }, to: { type: "contacts", id: "77" } },
          { from: { type: "companies", id: "18" }, to: { type: "deals", id: "42" } },
          { from: { type: "companies", id: "18" }, to: { type: "deals", id: "999" } },
        ] },
      { sequence: 4, call: 3, tool: "update_record", operation: "write", status: "attempted" },
      { sequence: 5, call: 3, tool: "update_record", operation: "write", status: "awaiting_commit" },
      { sequence: 6, call: 3, tool: "update_record", operation: "write", status: "committed", durationMs: 41, inputSummary: "deals #42", records: [{ type: "deals", id: "42" }] },
      { sequence: 7, call: 4, tool: "create_record", operation: "write", status: "attempted" },
      { sequence: 8, call: 4, tool: "create_record", operation: "write", status: "rolled_back", durationMs: 5, failure: "conflict", records: [] },
      { sequence: 9, call: 5, tool: "search_tickets", operation: "read", status: "completed", durationMs: 4, count: 0, total: 0, records: [] },
    ],
  };

  it("keeps the new sanitized fields and drops relations whose ends are not vouched for", () => {
    const value = projectEvidence(trace)!;
    expect(value.events[1]?.count).toBe(1);
    expect(value.events[2]?.relations).toHaveLength(2);
    expect(value.incomplete).toBe(true);
    expect(value.events[7]?.failure).toBe("conflict");
    expect(projectEvidence({ ...trace, events: [{ ...trace.events[1], failure: "conflict" }] })!.events[0]?.failure).toBeUndefined();
  });

  it("collapses events into calls with their checkpoint history and dedupes records and links", () => {
    const insights = deriveInsights(projectEvidence(trace)!);
    expect(insights.calls.map((call) => [call.step, call.status, call.history.length])).toEqual([[1, "completed", 2], [2, "completed", 1], [3, "committed", 3], [4, "rolled_back", 2], [5, "completed", 1]]);
    expect(insights.records.map((record) => record.key)).toEqual(["companies:18", "contacts:77", "deals:42"]);
    expect(insights.records.find((record) => record.key === "deals:42")?.written).toBe(true);
    expect(insights.records.find((record) => record.key === "companies:18")?.steps).toEqual([1, 2]);
    expect(insights.relations).toHaveLength(2);
    expect(insights).toMatchObject({ reads: 3, writes: 2, committed: 1, rolledBack: 1, unsuccessful: 1, totalMs: 89, verdict: "partial" });
  });

  it("derives observed limitations from events and labels interpretations separately", () => {
    const insights = deriveInsights(projectEvidence(trace)!);
    const observed = insights.limitations.filter((item) => item.basis === "observed").map((item) => item.text);
    expect(observed.some((text) => text.startsWith("Created a CRM record was refused because it conflicts"))).toBe(true);
    expect(observed.some((text) => text.startsWith("Searched tickets returned no matching records"))).toBe(true);
    expect(observed.some((text) => text.startsWith("The trace is partial"))).toBe(true);
    expect(insights.limitations.filter((item) => item.basis === "interpretation")).toHaveLength(1);
  });

  it("reads a dangling multi-candidate search as a probable clarification, as interpretation only", () => {
    const insights = deriveInsights(projectEvidence({
      version: 1, incomplete: false,
      events: [{ sequence: 1, call: 1, tool: "search_companies", operation: "read", status: "completed", count: 2, total: 2, records: [{ type: "companies", id: "1" }, { type: "companies", id: "2" }] }],
    })!);
    const reading = insights.limitations.filter((item) => item.basis === "interpretation");
    expect(reading[0]?.text).toContain("found 2 candidates");
    expect(insights.verdict).toBe("complete");
    expect(deriveInsights(projectEvidence({ version: 1, incomplete: false, events: [] })!).verdict).toBe("none");
  });
});

describe("grounding and write decision paths", () => {
  const extended = {
    version: 1,
    incomplete: false,
    events: [
      { sequence: 1, call: 1, tool: "search_deals", operation: "read", status: "completed", count: 2, total: 2, records: [{ type: "deals", id: "41" }, { type: "deals", id: "42" }] },
      { sequence: 2, call: 2, tool: "update_record", operation: "write", status: "committed", records: [{ type: "deals", id: "42" }], decisionPath: {
        searches: [1], candidates: 2, chosen: { type: "deals", id: "42", label: "Fornitura Mazza", detail: "Como" }, action: "Moved the deal to Won",
        automations: [{ rule: "R10", record: { type: "tickets", id: "88" } }],
      } },
    ],
    grounding: {
      facts: [
        { text: "12.345,67", kind: "amount", status: "grounded", event: 1 },
        { text: "buyer@example.it", kind: "email", status: "unverified", event: null },
      ],
      grounded: 1,
      unverified: 1,
    },
  };

  it("validates grounded facts and the read-to-write decision chain", () => {
    const projected = projectEvidence(extended)!;
    expect(projected.grounding).toEqual({
      facts: [
        { text: "12.345,67", kind: "amount", status: "grounded", event: 1 },
        { text: "buyer@example.it", kind: "email", status: "unverified" },
      ],
      grounded: 1,
      unverified: 1,
    });
    expect(projected.events[1]?.decisionPath).toEqual({
      searches: [1], candidates: 2, chosen: { type: "deals", id: "42", label: "Fornitura Mazza", detail: "Como" }, action: "Moved the deal to Won",
      automations: [{ rule: "R10", record: { type: "tickets", id: "88" } }],
    });
    expect(deriveInsights(projected).calls[1]?.decisionPath?.chosen).toEqual({ type: "deals", id: "42", label: "Fornitura Mazza", detail: "Como" });
  });

  it("fails closed when grounding points outside the trace or a decision references a non-read", () => {
    const malformed = structuredClone(extended);
    malformed.grounding.facts[0]!.event = 999;
    malformed.events[1]!.decisionPath!.searches = [2];
    const projected = projectEvidence(malformed)!;
    expect(projected.incomplete).toBe(true);
    expect(projected.grounding?.facts).toHaveLength(1);
    expect(projected.events[1]?.decisionPath?.searches).toEqual([]);
  });
});
