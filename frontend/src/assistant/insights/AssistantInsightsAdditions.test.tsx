import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { AssistantEvidence } from "@/api/types";
import { EvidenceInspector } from "../EvidenceInspector";

const value = {
  version: 1,
  incomplete: false,
  events: [
    { sequence: 1, call: 1, tool: "search_deals", operation: "read", status: "completed", count: 1, records: [{ type: "deals", id: "42" }] },
    { sequence: 2, call: 2, tool: "update_record", operation: "write", status: "committed", durationMs: 20, records: [{ type: "deals", id: "42" }], decisionPath: {
      searches: [1], candidates: 1, chosen: { type: "deals", id: "42", label: "Fornitura Mazza", detail: "Como" }, action: "Moved the deal to Won",
      automations: [{ rule: "R10", record: { type: "tickets", id: "88" } }],
    } },
  ],
  grounding: {
    facts: [
      { text: "12.345,67", kind: "amount", status: "grounded", event: 1 },
      { text: "42", kind: "record_id", status: "grounded", event: 1 },
      { text: "buyer@example.it", kind: "email", status: "grounded", event: 1 },
      { text: "10 ottobre 2026", kind: "date", status: "grounded", event: 1 },
      { text: "Fornitura Mazza", kind: "name", status: "grounded", event: 1 },
    ],
    grounded: 5,
    unverified: 0,
  },
} as unknown as AssistantEvidence;

describe("Assistant Insights additions", () => {
  it("renders grounding facts and the compact write decision path", () => {
    render(<MemoryRouter><EvidenceInspector value={value} /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: /Assistant Insights/ }));
    expect(screen.getByText("Read 1 record, changed 1 deal, triggered 1 automation, 5 of 5 facts found in CRM data.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Grounded facts 5 of 5" })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Facts checked against this turn's CRM tool outputs" })).toHaveTextContent("Fornitura Mazza");
    expect(screen.getByRole("list", { name: "What the assistant did in plain words" })).toHaveTextContent("Moved the deal to Won: saved");
    expect(screen.getByRole("link", { name: /Open Fornitura Mazza/ })).toHaveAttribute("href", "/deals/42");
    expect(screen.queryByText("Committed")).toBeNull();
    expect(screen.queryByText("20 ms")).toBeNull();
    expect(screen.getAllByText("Found in CRM")).toHaveLength(5);
    fireEvent.click(screen.getByRole("button", { name: "Details" }));
    const path = screen.getByRole("list", { name: "Decision path for write step 2" });
    expect(path).toHaveTextContent("QuestionYour request");
    expect(path).toHaveTextContent("Events 1 · 1 candidate");
    expect(path).toHaveTextContent("Fornitura Mazza(Como)#42");
    expect(path).toHaveTextContent("R10 kickoff ticket");
    expect(screen.getByText("20 ms")).toBeInTheDocument();
    expect(screen.getAllByText("Event 1")).toHaveLength(5);
  });

  it("uses warning semantics for unverified facts", () => {
    const warning = structuredClone(value) as unknown as Record<string, unknown>;
    warning.grounding = { facts: [{ text: "99.99", kind: "amount", status: "unverified", event: null }], grounded: 0, unverified: 1 };
    render(<MemoryRouter><EvidenceInspector value={warning as unknown as AssistantEvidence} /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: /Assistant Insights/ }));
    expect(screen.getByText("Unverified").closest("li")).toHaveClass("text-warn");
  });
});
