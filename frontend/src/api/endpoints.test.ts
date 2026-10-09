import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./transport", async () => {
  const { mockRequest } = await import("./mock/router");
  return { USING_MOCKS: true, call: mockRequest };
});

import * as api from "./endpoints";
import { resetMockDb } from "./mock/router";

describe("endpoints against the mock backend", () => {
  beforeEach(() => resetMockDb());

  it("lists companies sorted by name with a total", async () => {
    const page = await api.listCompanies({ limit: 10 });
    expect(page.results.length).toBe(10);
    expect(page.total).toBeGreaterThan(10);
    const names = page.results.map((c) => c.properties.name!);
    expect(names).toEqual([...names].sort((a, b) => a.localeCompare(b, "en", { sensitivity: "base" })));
    expect(page.paging?.next?.after).toBeDefined();
  });

  it("filters companies by class", async () => {
    const page = await api.listCompanies({ classe: "A", limit: 50 });
    expect(page.results.every((c) => c.properties.classe_cliente === "A")).toBe(true);
  });

  it("loads a company page with its contacts, deals and tickets", async () => {
    const first = (await api.listCompanies({ limit: 1 })).results[0]!;
    const page = await api.getCompanyPage(first.id);
    expect(page.company.id).toBe(first.id);
    expect(page.contacts.length).toBeGreaterThan(0);
    expect(page.contacts.every((c) => c.properties.associatedcompanyid === first.id)).toBe(true);
  });

  it("returns sorted pipelines", async () => {
    const pipelines = await api.getPipelines("deals");
    expect(pipelines[0]!.id).toBe("default");
    expect(pipelines[0]!.stages.map((s) => s.id)[0]).toBe("appointmentscheduled");
  });

  it("moves a deal and opens the supply kickoff ticket when it is won", async () => {
    const open = await api.dealsInStage("default", "contractsent");
    const deal = open.results[0]!;
    await api.moveDeal(deal.id, "closedwon");
    const page = await api.getDealPage(deal.id);
    expect(page.deal.properties.dealstage).toBe("closedwon");
    expect(page.tickets.some((t) => t.properties.subject?.startsWith("Avvio fornitura - "))).toBe(true);
  });

  it("reads the dormant customers list", async () => {
    const res = await api.getDormantCompanies();
    expect(res.list?.name).toBe("Clienti dormienti");
    expect(res.companies.length).toBeGreaterThan(0);
  });

  it("collects activities for a set of contacts and deals", async () => {
    const first = (await api.listCompanies({ limit: 3 })).results;
    const page = await api.getCompanyPage(first[0]!.id);
    const acts = await api.activitiesFor([
      { type: "contacts", ids: page.contacts.map((c) => c.id) },
      { type: "deals", ids: page.deals.map((d) => d.id) },
    ]);
    for (let i = 1; i < acts.length; i++) {
      expect(Date.parse(acts[i - 1]!.timestamp!)).toBeGreaterThanOrEqual(Date.parse(acts[i]!.timestamp!));
    }
  });

  it("adds a note to a company", async () => {
    const first = (await api.listCompanies({ limit: 1 })).results[0]!;
    const note = await api.createNote("Chiamare lunedì", "anna.sala@brambillaforniture.it", { type: "companies", id: first.id });
    expect(note.properties.hs_note_body).toBe("Chiamare lunedì");
    const acts = await api.activitiesFor([{ type: "companies", ids: [first.id] }]);
    expect(acts.some((a) => a.body === "Chiamare lunedì")).toBe(true);
  });

  it("answers the assistant contract", async () => {
    const res = await api.askAssistant({
      context: { now: "2026-12-02T10:00:00+01:00", user: "mattia.vigano@brambillaforniture.it" },
      messages: [{ role: "user", content: "Quanto abbiamo fatturato con Nuova Tessile Spinelli nel 2025?" }],
    });
    expect(res.reply).toMatch(/Nuova Tessile Spinelli/);
  });
});
