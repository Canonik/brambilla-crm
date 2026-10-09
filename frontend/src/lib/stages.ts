// Pipelines and stages come from the API with the labels Brambilla asked for,
// several of which are Italian. The UI is English, so we translate the labels
// we know and fall back to whatever the backend sends.

export type StageLike = {
  id: string;
  label: string;
  metadata?: { isClosed?: string | boolean; probability?: string | number };
};

export type PipelineLike = { id: string; label: string };

export type Tone = "brand" | "signal" | "good" | "warn" | "bad" | "muted" | "neutral" | "none";

const SALES_STAGE_LABELS: Record<string, string> = {
  appointmentscheduled: "Appointment",
  qualifiedtobuy: "Qualified",
  presentationscheduled: "Presentation",
  decisionmakerboughtin: "Decision maker",
  contractsent: "Contract sent",
  closedwon: "Won",
  closedlost: "Lost",
};

const LABEL_TRANSLATIONS: Record<string, string> = {
  "da rinnovare": "To renew",
  "in trattativa": "Negotiating",
  rinnovato: "Renewed",
  "non rinnovato": "Not renewed",
  aperto: "Open",
  "in lavorazione": "In progress",
  "in attesa del cliente": "Waiting on customer",
  chiuso: "Closed",
  "closed won": "Won",
  "closed lost": "Lost",
  "appointment scheduled": "Appointment",
  "qualified to buy": "Qualified",
  "presentation scheduled": "Presentation",
  "decision maker bought-in": "Decision maker",
  "contract sent": "Contract sent",
};

const PIPELINE_TRANSLATIONS: Record<string, string> = {
  "sales pipeline": "Sales",
  vendite: "Sales",
  rinnovi: "Renewals",
  assistenza: "Support",
  "support pipeline": "Support",
};

export function displayStageLabel(stage: StageLike | undefined | null): string {
  if (!stage) return "Unknown stage";
  const byId = SALES_STAGE_LABELS[stage.id];
  if (byId) return byId;
  const key = (stage.label ?? "").trim().toLowerCase();
  return LABEL_TRANSLATIONS[key] ?? stage.label ?? stage.id;
}

export function displayPipelineLabel(pipeline: PipelineLike | undefined | null): string {
  if (!pipeline) return "Pipeline";
  if (pipeline.id === "default") return "Sales";
  const key = (pipeline.label ?? "").trim().toLowerCase();
  return PIPELINE_TRANSLATIONS[key] ?? pipeline.label ?? pipeline.id;
}

function probabilityOf(stage: StageLike): number | null {
  const p = stage.metadata?.probability;
  if (p === undefined || p === null || p === "") return null;
  const n = Number(p);
  return Number.isFinite(n) ? n : null;
}

function isClosed(stage: StageLike): boolean {
  const c = stage.metadata?.isClosed;
  return c === true || c === "true";
}

export function isWonStage(stage: StageLike | undefined | null): boolean {
  if (!stage) return false;
  if (stage.id === "closedwon") return true;
  const label = (stage.label ?? "").trim().toLowerCase();
  if (label === "rinnovato" || label === "closed won" || label === "won" || label === "vinta") return true;
  return isClosed(stage) && probabilityOf(stage) === 1;
}

export function isLostStage(stage: StageLike | undefined | null): boolean {
  if (!stage) return false;
  if (stage.id === "closedlost") return true;
  const label = (stage.label ?? "").trim().toLowerCase();
  if (label === "non rinnovato" || label === "closed lost" || label === "lost" || label === "persa") return true;
  return isClosed(stage) && probabilityOf(stage) === 0;
}

export function isClosedStage(stage: StageLike | undefined | null): boolean {
  if (!stage) return false;
  return isWonStage(stage) || isLostStage(stage) || isClosed(stage);
}

export function stageTone(stage: StageLike | undefined | null): Tone {
  if (!stage) return "neutral";
  if (isWonStage(stage)) return "good";
  if (isLostStage(stage)) return "muted";
  const label = (stage.label ?? "").trim().toLowerCase();
  if (label === "in attesa del cliente") return "warn";
  if (label === "chiuso" || label === "closed") return "muted";
  return "brand";
}

export function classTone(value: string | null | undefined): Tone {
  switch ((value ?? "").trim().toUpperCase()) {
    case "A":
      return "signal";
    case "B":
      return "brand";
    case "C":
      return "neutral";
    default:
      return "none";
  }
}

export function priorityMeta(value: string | null | undefined): { label: string; tone: Tone; rank: number } {
  switch ((value ?? "").trim().toUpperCase()) {
    case "URGENT":
      return { label: "Urgent", tone: "bad", rank: 4 };
    case "HIGH":
      return { label: "High", tone: "signal", rank: 3 };
    case "MEDIUM":
      return { label: "Medium", tone: "brand", rank: 2 };
    case "LOW":
      return { label: "Low", tone: "muted", rank: 1 };
    default:
      return { label: "No priority", tone: "none", rank: 0 };
  }
}

export const LIFECYCLE_LABELS: Record<string, string> = {
  lead: "Lead",
  opportunity: "Prospect",
  customer: "Customer",
  other: "Former customer",
  subscriber: "Subscriber",
  marketingqualifiedlead: "Marketing qualified",
  salesqualifiedlead: "Sales qualified",
  evangelist: "Evangelist",
};

export function lifecycleLabel(value: string | null | undefined): string {
  const key = (value ?? "").trim().toLowerCase();
  if (!key) return "No stage";
  return LIFECYCLE_LABELS[key] ?? value!;
}

export function lifecycleTone(value: string | null | undefined): Tone {
  switch ((value ?? "").trim().toLowerCase()) {
    case "customer":
      return "good";
    case "opportunity":
      return "brand";
    case "lead":
      return "neutral";
    case "other":
      return "muted";
    default:
      return "none";
  }
}
