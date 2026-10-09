import { CircleCheck, CircleDot, CircleX, Clock, Flame } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import type { Stage } from "@/api/types";
import {
  displayStageLabel,
  isClosedTicketStage,
  isLostStage,
  isWonStage,
  lifecycleLabel,
  lifecycleTone,
  priorityMeta,
  stageTone,
} from "@/lib/stages";

export function StageBadge({ stage, stageId, size }: { stage?: Stage | null; stageId?: string | null; size?: "sm" | "md" }) {
  if (!stage) {
    return (
      <Badge tone="none" size={size}>
        {stageId ?? "No stage"}
      </Badge>
    );
  }
  const won = isWonStage(stage);
  const lost = isLostStage(stage);
  return (
    <Badge
      tone={stageTone(stage)}
      size={size}
      icon={won ? <CircleCheck className="size-3" /> : lost ? <CircleX className="size-3" /> : <CircleDot className="size-3" />}
    >
      {displayStageLabel(stage)}
    </Badge>
  );
}

export function TicketStageBadge({ stage, stageId, size }: { stage?: Stage | null; stageId?: string | null; size?: "sm" | "md" }) {
  if (!stage) {
    return (
      <Badge tone="none" size={size}>
        {stageId ?? "No status"}
      </Badge>
    );
  }
  const tone = stageTone(stage);
  const closed = isClosedTicketStage(stage);
  return (
    <Badge
      tone={closed ? "muted" : tone === "warn" ? "warn" : "brand"}
      size={size}
      icon={closed ? <CircleCheck className="size-3" /> : tone === "warn" ? <Clock className="size-3" /> : <CircleDot className="size-3" />}
    >
      {displayStageLabel(stage)}
    </Badge>
  );
}

export function PriorityBadge({ value, size }: { value: string | null | undefined; size?: "sm" | "md" }) {
  const meta = priorityMeta(value);
  return (
    <Badge tone={meta.tone} size={size} icon={meta.rank >= 3 ? <Flame className="size-3" /> : undefined} dot={meta.rank > 0 && meta.rank < 3}>
      {meta.label}
    </Badge>
  );
}

export function LifecycleBadge({ value, size }: { value: string | null | undefined; size?: "sm" | "md" }) {
  return (
    <Badge tone={lifecycleTone(value)} size={size} dot={Boolean(value)}>
      {lifecycleLabel(value)}
    </Badge>
  );
}
