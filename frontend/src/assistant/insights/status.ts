import type { EvidenceStatus } from "@/api/types";
import type { Tone } from "@/lib/stages";

export const STATUS_LABELS: Record<EvidenceStatus, string> = {
  attempted: "Attempted",
  completed: "Completed",
  failed: "Failed",
  awaiting_commit: "Returned, commit unconfirmed",
  committed: "Commit confirmed",
  rolled_back: "Rolled back",
  unknown: "Outcome unknown",
};

export const STATUS_TONES: Record<EvidenceStatus, Tone> = {
  attempted: "muted",
  completed: "good",
  failed: "bad",
  awaiting_commit: "warn",
  committed: "good",
  rolled_back: "bad",
  unknown: "warn",
};

export function formatMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(ms >= 10_000 ? 0 : 1)} s` : `${ms} ms`;
}
