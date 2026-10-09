import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  pointerWithin,
  rectIntersection,
  type CollisionDetection,
  type KeyboardCoordinateGetter,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { useQueryClient, type InfiniteData } from "@tanstack/react-query";
import { CircleCheck, CircleX, Kanban } from "lucide-react";
import { keys, useDealCompanies, useDealsInStage, useMoveDeal, usePipelines } from "@/api/hooks";
import type { Company, Deal, Paged, Pipeline, Stage } from "@/api/types";
import { useCurrentUser } from "@/app/currentUser";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Avatar } from "@/components/ui/Avatar";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toaster";
import { DateText, Money } from "@/components/crm/Values";
import { cn } from "@/lib/cn";
import { formatMoney, formatNumber } from "@/lib/format";
import { sumEur } from "@/lib/money";
import { displayPipelineLabel, displayStageLabel, isLostStage, isWonStage } from "@/lib/stages";
import { useListParams } from "@/lib/useListParams";
import { userName } from "@/api/users";

// Pointer drags are matched by the cursor position; keyboard drags have no
// cursor, so they fall back to the overlap of the moving card with a column.
const collision: CollisionDetection = (args) => {
  const hits = pointerWithin(args);
  return hits.length ? hits : rectIntersection(args);
};

// Left and right arrows jump one column (cards are 288px wide plus a 12px gap).
const columnStep: KeyboardCoordinateGetter = (event, { currentCoordinates }) => {
  if (event.code === "ArrowRight") return { ...currentCoordinates, x: currentCoordinates.x + 300 };
  if (event.code === "ArrowLeft") return { ...currentCoordinates, x: currentCoordinates.x - 300 };
  return undefined;
};

const KEYS = ["pipeline", "mine"] as const;
const DEFAULTS = { pipeline: "default" } as const;

export function DealsBoard() {
  const pipelines = usePipelines("deals");
  const [params, setParams] = useListParams(KEYS, DEFAULTS);
  const { user } = useCurrentUser();
  const pipeline = pipelines.data?.find((p) => p.id === params.pipeline) ?? pipelines.data?.[0];
  const [active, setActive] = useState<Deal | null>(null);
  const move = useMoveDeal(pipeline);
  const qc = useQueryClient();
  const toast = useToast();
  const mine = params.mine === "1";

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: columnStep }),
  );

  const onDragStart = (e: DragStartEvent) => setActive((e.active.data.current as { deal: Deal } | undefined)?.deal ?? null);

  const onDragEnd = async (e: DragEndEvent) => {
    setActive(null);
    const deal = (e.active.data.current as { deal: Deal } | undefined)?.deal;
    const toStage = e.over?.id ? String(e.over.id).replace(/^bar:/, "") : null;
    if (!deal || !toStage || !pipeline) return;
    const fromStage = deal.properties.dealstage ?? "";
    if (toStage === fromStage) return;

    type Data = InfiniteData<Paged<Deal>, string | undefined>;
    const fromKey = keys.dealsInStage(pipeline.id, fromStage);
    const toKey = keys.dealsInStage(pipeline.id, toStage);
    const prevFrom = qc.getQueryData<Data>(fromKey);
    const prevTo = qc.getQueryData<Data>(toKey);
    const moved: Deal = { ...deal, properties: { ...deal.properties, dealstage: toStage, hs_lastmodifieddate: new Date().toISOString() } };
    qc.setQueryData<Data>(fromKey, (d) =>
      d
        ? {
            ...d,
            pages: d.pages.map((p, i) => ({ ...p, results: p.results.filter((x) => x.id !== deal.id), total: i === 0 && p.total !== undefined ? p.total - 1 : p.total })),
          }
        : d,
    );
    qc.setQueryData<Data>(toKey, (d) =>
      d
        ? {
            ...d,
            pages: d.pages.map((p, i) => (i === 0 ? { ...p, results: [moved, ...p.results], total: p.total !== undefined ? p.total + 1 : p.total } : p)),
          }
        : d,
    );
    try {
      await move.mutateAsync({ deal, toStage });
      const stage = pipeline.stages.find((s) => s.id === toStage);
      toast.success(`Moved to ${displayStageLabel(stage)}`, deal.properties.dealname ?? undefined);
    } catch (err) {
      qc.setQueryData(fromKey, prevFrom);
      qc.setQueryData(toKey, prevTo);
      toast.error("Could not move the deal", err instanceof Error ? err.message : undefined);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col">
      <PageHeader
        title="Deals"
        meta={pipeline ? <span>{displayPipelineLabel(pipeline)} pipeline · drag a card to change its stage</span> : undefined}
        actions={
          <Button variant={mine ? "primary" : "secondary"} size="md" onClick={() => setParams({ mine: mine ? "" : "1" })} aria-pressed={mine}>
            <Avatar name={user.name} size="xs" className={mine ? "bg-white/20 text-white" : undefined} />
            My deals
          </Button>
        }
      >
        {pipelines.data?.length ? (
          <div className="-mb-px flex items-end gap-0.5">
            {pipelines.data.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => setParams({ pipeline: p.id })}
                className={cn(
                  "inline-flex h-9 items-center border-b-2 px-3 text-[13px] font-medium transition-colors",
                  p.id === pipeline?.id ? "border-gentian text-ink" : "border-transparent text-ink-2 hover:text-ink",
                )}
                aria-current={p.id === pipeline?.id ? "page" : undefined}
              >
                {displayPipelineLabel(p)}
              </button>
            ))}
          </div>
        ) : (
          <div className="h-9" />
        )}
      </PageHeader>

      {pipelines.isPending ? (
        <div className="flex gap-3 overflow-hidden p-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-[60vh] w-72 shrink-0 rounded-lg" />
          ))}
        </div>
      ) : pipelines.isError ? (
        <ErrorState error={pipelines.error} onRetry={() => pipelines.refetch()} title="Could not load the pipelines" />
      ) : !pipeline ? (
        <EmptyState icon={<Kanban />} title="No pipelines yet" description="Pipelines are created by the reset and the migration." />
      ) : (
        <DndContext sensors={sensors} collisionDetection={collision} onDragStart={onDragStart} onDragEnd={onDragEnd} onDragCancel={() => setActive(null)}>
          <div className="relative flex min-h-0 flex-1 flex-col">
            <div className="flex min-h-0 flex-1 gap-3 overflow-x-auto scroll-quiet p-4" data-board>
              {pipeline.stages.map((stage) => (
                <Column key={stage.id} pipeline={pipeline} stage={stage} owner={mine ? user.email : undefined} />
              ))}
            </div>
            {active ? <ClosedStageBar stages={pipeline.stages.filter((s) => isWonStage(s) || isLostStage(s))} current={active.properties.dealstage ?? ""} /> : null}
          </div>
          <DragOverlay dropAnimation={null}>{active ? <DealCard deal={active} overlay /> : null}</DragOverlay>
        </DndContext>
      )}
    </div>
  );
}

/** While a card is being dragged, Won and Lost are one drop away even when
 *  their columns are scrolled out of view. */
function ClosedStageBar({ stages, current }: { stages: Stage[]; current: string }) {
  if (stages.length === 0) return null;
  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 flex justify-center gap-3 p-4">
      {stages.map((s) => (
        <BarTarget key={s.id} stage={s} disabled={s.id === current} />
      ))}
    </div>
  );
}

function BarTarget({ stage, disabled }: { stage: Stage; disabled: boolean }) {
  const won = isWonStage(stage);
  const { isOver, setNodeRef } = useDroppable({ id: `bar:${stage.id}`, disabled });
  return (
    <div
      ref={setNodeRef}
      className={cn(
        "pointer-events-auto flex h-14 w-64 items-center justify-center gap-2 rounded-lg border-2 border-dashed bg-surface/95 text-[13px] font-medium shadow-pop backdrop-blur transition-colors",
        disabled && "opacity-40",
        isOver ? (won ? "border-good bg-good-soft text-good" : "border-ink-2 bg-surface-3 text-ink") : won ? "border-good/50 text-good" : "border-line-strong text-ink-2",
      )}
    >
      {won ? <CircleCheck className="size-4" aria-hidden /> : <CircleX className="size-4" aria-hidden />}
      Drop to mark {displayStageLabel(stage).toLowerCase()}
    </div>
  );
}

function Column({ pipeline, stage, owner }: { pipeline: Pipeline; stage: Stage; owner?: string }) {
  const query = useDealsInStage(pipeline.id, stage.id);
  const { isOver, setNodeRef } = useDroppable({ id: stage.id });
  const all = query.data?.pages.flatMap((p) => p.results) ?? [];
  const deals = owner ? all.filter((d) => d.properties.commerciale === owner) : all;
  const companies = useDealCompanies(all.map((d) => d.id));
  const total = query.data?.pages[0]?.total;
  const sum = useMemo(() => sumEur(deals.map((d) => ({ amount: d.properties.amount, currency: d.properties.deal_currency_code }))), [deals]);
  const won = isWonStage(stage);
  const lost = isLostStage(stage);

  return (
    <section
      ref={setNodeRef}
      aria-label={`${displayStageLabel(stage)} column`}
      className={cn(
        "flex h-full w-72 shrink-0 flex-col rounded-lg border bg-surface-2 transition-colors",
        isOver ? "border-gentian bg-gentian-soft/40" : "border-line",
      )}
    >
      <header className="flex items-start justify-between gap-2 px-3 pt-3 pb-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className={cn("size-2 shrink-0 rounded-full", won ? "bg-good" : lost ? "bg-ink-3" : "bg-gentian")} aria-hidden />
            <h2 className="truncate text-[13px] font-semibold text-ink">{displayStageLabel(stage)}</h2>
            <span className="text-[12px] text-ink-3 tnum">{total !== undefined ? formatNumber(owner ? deals.length : total) : ""}</span>
          </div>
          <div className="mt-0.5 pl-4 text-[12px] text-ink-2 tnum" title={sum.skipped ? `${sum.skipped} without amount not counted` : undefined}>
            {deals.length ? formatMoney(sum.total, "EUR", { compact: true }) : "–"}
            {total !== undefined && all.length < total && !owner ? (
              <span className="text-ink-3">
                {" "}
                · {formatNumber(all.length)} of {formatNumber(total)} loaded
              </span>
            ) : null}
          </div>
        </div>
      </header>
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto scroll-quiet px-2 pb-2">
        {query.isPending ? (
          Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-20 w-full rounded-md" />)
        ) : query.isError ? (
          <ErrorState error={query.error} onRetry={() => query.refetch()} compact title="Could not load" />
        ) : deals.length === 0 ? (
          <div className="rounded-md border border-dashed border-line-strong px-3 py-6 text-center text-[12px] text-ink-3">
            {owner ? "None of your deals here" : "No deals in this stage"}
          </div>
        ) : (
          deals.map((d) => <DealCard key={d.id} deal={d} company={companies.data?.[d.id]} />)
        )}
        {query.hasNextPage && !owner ? (
          <Button variant="ghost" size="sm" className="w-full" loading={query.isFetchingNextPage} onClick={() => query.fetchNextPage()}>
            Load more
          </Button>
        ) : null}
      </div>
    </section>
  );
}

function DealCard({ deal, overlay, company }: { deal: Deal; overlay?: boolean; company?: Company }) {
  const navigate = useNavigate();
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: deal.id, data: { deal }, disabled: overlay });
  const p = deal.properties;
  return (
    <article
      ref={overlay ? undefined : setNodeRef}
      {...(overlay ? {} : { ...attributes, ...listeners })}
      onClick={() => {
        if (!overlay && !isDragging) navigate(`/deals/${deal.id}`);
      }}
      onKeyDown={(e) => {
        // Enter opens the deal; Space and the arrows belong to the drag sensor.
        if (e.key === "Enter" && !overlay) navigate(`/deals/${deal.id}`);
        else if (!overlay) listeners?.onKeyDown?.(e);
      }}
      className={cn(
        "cursor-grab rounded-md border border-line bg-surface px-3 py-2.5 text-left shadow-card outline-none transition-shadow",
        "hover:border-line-strong focus-visible:ring-2 focus-visible:ring-gentian/40",
        isDragging && "opacity-40",
        overlay && "w-72 cursor-grabbing rotate-[1.5deg] shadow-drag",
      )}
      aria-roledescription="draggable deal"
    >
      <div className="line-clamp-2 text-[13px] font-medium leading-snug text-ink">{p.dealname || "Untitled deal"}</div>
      {company ? <div className="mt-0.5 truncate text-[12px] text-ink-3">{company.properties.name}</div> : null}
      <div className="mt-1.5 flex items-center justify-between gap-2">
        <Money amount={p.amount} currency={p.deal_currency_code} className="text-[13px] font-semibold" />
        <DateText value={p.closedate} className="text-[12px] text-ink-3" />
      </div>
      <div className="mt-2 flex items-center gap-1.5 text-[12px] text-ink-2">
        {p.commerciale ? (
          <>
            <Avatar name={userName(p.commerciale)} size="xs" />
            <span className="truncate">{userName(p.commerciale)}</span>
          </>
        ) : (
          <span className="text-ink-3">Unassigned</span>
        )}
      </div>
    </article>
  );
}
