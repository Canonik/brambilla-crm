import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { LifeBuoy } from "lucide-react";
import { usePipelines, useTickets } from "@/api/hooks";
import type { TicketListParams } from "@/api/endpoints";
import { useCurrentUser } from "@/app/currentUser";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { NativeSelect, SearchInput } from "@/components/ui/Input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { SkeletonRows } from "@/components/ui/Skeleton";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { LoadMoreFooter } from "@/components/ui/LoadMore";
import { Avatar } from "@/components/ui/Avatar";
import { PriorityBadge, TicketStageBadge } from "@/components/crm/Badges";
import { DateText, OwnerChip, RelativeTime } from "@/components/crm/Values";
import { useListParams } from "@/lib/useListParams";
import { formatNumber, truncate } from "@/lib/format";
import { useDebounced } from "@/lib/useDebounced";
import { displayStageLabel, isClosedTicketStage, pickSupportPipeline } from "@/lib/stages";
import { cn } from "@/lib/cn";

const KEYS = ["q", "status", "priority", "scope", "mine"] as const;
const DEFAULTS = { scope: "open" } as const;

export function TicketsList() {
  const navigate = useNavigate();
  const { user } = useCurrentUser();
  const [params, setParams] = useListParams(KEYS, DEFAULTS);
  const q = useDebounced(params.q, 250);
  const pipelines = usePipelines("tickets");
  const support = pickSupportPipeline(pipelines.data);
  const stages = useMemo(() => support?.stages ?? [], [support]);
  const allStages = useMemo(() => pipelines.data?.flatMap((p) => p.stages) ?? [], [pipelines.data]);
  const closedIds = useMemo(() => allStages.filter((s) => isClosedTicketStage(s)).map((s) => s.id), [allStages]);
  const mine = params.mine === "1";

  const queryParams = useMemo<TicketListParams>(
    () => ({
      query: q,
      stage: params.status || undefined,
      priority: params.priority || undefined,
      owner: mine ? user.email : undefined,
      openOnly: params.scope === "open" && !params.status,
      closedStageIds: closedIds,
    }),
    [q, params.status, params.priority, params.scope, mine, user.email, closedIds],
  );
  const query = useTickets(queryParams);
  const rows = query.data?.pages.flatMap((p) => p.results) ?? [];
  const total = query.data?.pages[0]?.total;
  const stageOf = (id: string | null | undefined) => allStages.find((s) => s.id === id);

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Tickets"
        meta={total !== undefined ? <span className="tnum">{formatNumber(total)} {params.scope === "open" && !params.status ? "open" : ""} tickets</span> : undefined}
        actions={
          <Button variant={mine ? "primary" : "secondary"} onClick={() => setParams({ mine: mine ? "" : "1" })} aria-pressed={mine}>
            <Avatar name={user.name} size="xs" className={mine ? "bg-white/20 text-white" : undefined} />
            Assigned to me
          </Button>
        }
      >
        <div className="flex flex-wrap items-center gap-2 pb-3">
          <div className="inline-flex rounded-md border border-line-strong p-0.5">
            {[
              { value: "open", label: "Open" },
              { value: "all", label: "All" },
            ].map((o) => (
              <button
                key={o.value}
                type="button"
                onClick={() => setParams({ scope: o.value, status: "" })}
                className={cn("h-7 rounded-sm px-2.5 text-[12.5px] font-medium", params.scope === o.value && !params.status ? "bg-ink text-white" : "text-ink-2 hover:text-ink")}
                aria-pressed={params.scope === o.value && !params.status}
              >
                {o.label}
              </button>
            ))}
          </div>
          <SearchInput value={params.q} onChange={(v) => setParams({ q: v })} placeholder="Search subject or description" className="w-72" />
          <NativeSelect
            aria-label="Status"
            value={params.status}
            onChange={(e) => setParams({ status: e.target.value })}
            placeholder="Any status"
            options={stages.map((s) => ({ value: s.id, label: displayStageLabel(s) }))}
            className="w-44"
          />
          <NativeSelect
            aria-label="Priority"
            value={params.priority}
            onChange={(e) => setParams({ priority: e.target.value })}
            placeholder="Any priority"
            options={[
              { value: "URGENT", label: "Urgent" },
              { value: "HIGH", label: "High" },
              { value: "MEDIUM", label: "Medium" },
              { value: "LOW", label: "Low" },
            ]}
            className="w-40"
          />
        </div>
      </PageHeader>

      <div className="flex-1 bg-surface">
        {query.isPending || (pipelines.isPending && rows.length === 0) ? (
          <SkeletonRows rows={10} cols={6} />
        ) : query.isError ? (
          <ErrorState error={query.error} onRetry={() => query.refetch()} title="Could not load tickets" />
        ) : rows.length === 0 ? (
          <EmptyState
            icon={<LifeBuoy />}
            title={q || params.status || params.priority || mine ? "No tickets match" : params.scope === "open" ? "No open tickets" : "No tickets yet"}
            description={q || params.status || params.priority || mine ? "Try different filters." : params.scope === "open" ? "Nothing is waiting on support right now." : "Tickets arrive with the migration, and the CRM opens one each time a deal is won."}
          />
        ) : (
          <>
            <Table>
              <THead>
                <TR>
                  <TH>Ticket</TH>
                  <TH>Status</TH>
                  <TH>Priority</TH>
                  <TH>Owner</TH>
                  <TH align="right">Opened</TH>
                  <TH align="right">Closed</TH>
                </TR>
              </THead>
              <TBody>
                {rows.map((t) => (
                  <TR key={t.id} interactive onClick={() => navigate(`/tickets/${t.id}`)}>
                    <TD>
                      <div className="min-w-0 max-w-xl">
                        <div className="truncate font-medium text-ink">{t.properties.subject || "Untitled ticket"}</div>
                        {t.properties.content ? <div className="truncate text-[12px] text-ink-3">{truncate(t.properties.content.replace(/\s+/g, " "), 110)}</div> : null}
                      </div>
                    </TD>
                    <TD>
                      <TicketStageBadge stage={stageOf(t.properties.hs_pipeline_stage)} stageId={t.properties.hs_pipeline_stage} size="sm" />
                    </TD>
                    <TD>
                      <PriorityBadge value={t.properties.hs_ticket_priority} size="sm" />
                    </TD>
                    <TD>
                      <OwnerChip email={t.properties.assegnatario} size="xs" />
                    </TD>
                    <TD align="right" muted>
                      <RelativeTime value={t.properties.createdate} />
                    </TD>
                    <TD align="right" muted>
                      <DateText value={t.properties.closed_date} />
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
            <LoadMoreFooter shown={rows.length} total={total} hasMore={Boolean(query.hasNextPage)} loading={query.isFetchingNextPage} onMore={() => query.fetchNextPage()} noun="tickets" />
          </>
        )}
      </div>
    </div>
  );
}
