import { describe, expect, it } from "vitest";
import {
  classTone,
  displayPipelineLabel,
  displayStageLabel,
  isLostStage,
  isWonStage,
  priorityMeta,
  stageTone,
} from "./stages";

describe("displayStageLabel", () => {
  it("translates the default sales stage ids", () => {
    expect(displayStageLabel({ id: "closedwon", label: "Closed Won" })).toBe("Won");
    expect(displayStageLabel({ id: "appointmentscheduled", label: "Appointment Scheduled" })).toBe(
      "Appointment",
    );
  });
  it("translates Brambilla's Italian custom stage labels", () => {
    expect(displayStageLabel({ id: "123", label: "Da rinnovare" })).toBe("To renew");
    expect(displayStageLabel({ id: "124", label: "In attesa del cliente" })).toBe(
      "Waiting on customer",
    );
  });
  it("falls back to the backend label", () => {
    expect(displayStageLabel({ id: "x", label: "Something else" })).toBe("Something else");
  });
});

describe("displayPipelineLabel", () => {
  it("translates known pipelines", () => {
    expect(displayPipelineLabel({ id: "default", label: "Sales Pipeline" })).toBe("Sales");
    expect(displayPipelineLabel({ id: "9", label: "Rinnovi" })).toBe("Renewals");
    expect(displayPipelineLabel({ id: "10", label: "Assistenza" })).toBe("Support");
  });
});

describe("won and lost detection", () => {
  it("reads sales ids and renewal labels", () => {
    expect(isWonStage({ id: "closedwon", label: "Closed Won" })).toBe(true);
    expect(isWonStage({ id: "7", label: "Rinnovato", metadata: { isClosed: "true", probability: "1.0" } })).toBe(true);
    expect(isLostStage({ id: "closedlost", label: "Closed Lost" })).toBe(true);
    expect(isLostStage({ id: "8", label: "Non rinnovato", metadata: { isClosed: "true", probability: "0.0" } })).toBe(true);
    expect(isWonStage({ id: "qualifiedtobuy", label: "Qualified" })).toBe(false);
  });
});

describe("tones", () => {
  it("maps stages to a tone", () => {
    expect(stageTone({ id: "closedwon", label: "Closed Won" })).toBe("good");
    expect(stageTone({ id: "closedlost", label: "Closed Lost" })).toBe("muted");
    expect(stageTone({ id: "contractsent", label: "Contract" })).toBe("brand");
  });
  it("maps customer classes to a tone", () => {
    expect(classTone("A")).toBe("signal");
    expect(classTone("B")).toBe("brand");
    expect(classTone("C")).toBe("neutral");
    expect(classTone("")).toBe("none");
  });
  it("describes ticket priorities", () => {
    expect(priorityMeta("URGENT").label).toBe("Urgent");
    expect(priorityMeta("LOW").tone).toBe("muted");
    expect(priorityMeta(undefined).label).toBe("No priority");
  });
});
