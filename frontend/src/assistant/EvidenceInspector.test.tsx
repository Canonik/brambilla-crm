import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { EvidenceInspector } from "./EvidenceInspector";
import type { AssistantEvidence } from "@/api/types";

const value: AssistantEvidence = {
  version: 1,
  incomplete: false,
  events: [
    { sequence: 1, call: 1, tool: "search_companies", operation: "read", status: "attempted" },
    { sequence: 2, call: 1, tool: "search_companies", operation: "read", status: "completed", durationMs: 12, inputSummary: "Company lookup", records: [{ type: "companies", id: "18" }], ...( { count: 1, total: 1 } as object) },
    { sequence: 3, call: 2, tool: "revenue", operation: "read", status: "completed", durationMs: 27, inputSummary: "Revenue for company #18 in 2025",
      records: [{ type: "companies", id: "18" }, { type: "deals", id: "42" }],
      calculation: { kind: "sum_money_v1", policy: "brambilla_revenue_v1", currency: "EUR", populationComplete: true, populationCount: 1, terms: [{ record: { type: "deals", id: "42" }, amount: "12500.00" }], result: "12500.00", year: 2025 },
      ...({ relations: [{ from: { type: "companies", id: "18" }, to: { type: "deals", id: "42" } }] } as object) },
  ],
};

function mount(trace: AssistantEvidence = value) {
  return render(<MemoryRouter><EvidenceInspector value={trace} /></MemoryRouter>);
}

describe("EvidenceInspector", () => {
  it("renders nothing for a malformed envelope and a collapsed summary for a valid one", () => {
    const { container } = render(<MemoryRouter><EvidenceInspector value={{ version: 2 } as unknown as AssistantEvidence} /></MemoryRouter>);
    expect(container).toBeEmptyDOMElement();
    mount();
    const toggle = screen.getByRole("button", { name: /Assistant Insights/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveTextContent("2 operations · 2 records · 39 ms in the CRM");
    expect(screen.queryByRole("tablist")).toBeNull();
  });

  it("opens to the timeline and moves between views with the keyboard", () => {
    mount();
    fireEvent.click(screen.getByRole("button", { name: /Assistant Insights/ }));
    expect(screen.getByRole("status")).toHaveTextContent("Every observed operation settled");
    expect(screen.getByRole("list", { name: "Observed operations in order" })).toHaveTextContent("Calculated revenue");
    const actions = screen.getByRole("tab", { name: /Actions/ });
    expect(actions).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(actions, { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: /Evidence/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("group", { name: "2 records and 1 observed links" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Companies 18" })).toHaveAttribute("href", "/companies/18");
    fireEvent.keyDown(screen.getByRole("tab", { name: /Evidence/ }), { key: "End" });
    expect(screen.getByRole("tab", { name: /Limits/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText(/Interpretation, not observation/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Calculation/ }));
    expect(screen.getByText("Re-added in the browser: matches")).toBeInTheDocument();
    expect(screen.getAllByText(/12\.500,00/)).toHaveLength(2);
  });

  it("shows write checkpoints so a returned tool is not mistaken for a commit", () => {
    mount({
      version: 1, incomplete: false,
      events: [
        { sequence: 1, call: 1, tool: "update_record", operation: "write", status: "attempted" },
        { sequence: 2, call: 1, tool: "update_record", operation: "write", status: "awaiting_commit" },
        { sequence: 3, call: 1, tool: "update_record", operation: "write", status: "committed", durationMs: 40, inputSummary: "deals #42", records: [{ type: "deals", id: "42" }] },
      ],
    });
    fireEvent.click(screen.getByRole("button", { name: /Assistant Insights/ }));
    const checkpoints = screen.getByRole("list", { name: "Write checkpoints" });
    expect(checkpoints).toHaveTextContent("Requested");
    expect(checkpoints).toHaveTextContent("Store returned");
    expect(checkpoints).toHaveTextContent("Commit confirmed");
    expect(screen.getByRole("button", { name: /Assistant Insights/ })).toHaveTextContent("1 of 1 write committed");
  });
});
