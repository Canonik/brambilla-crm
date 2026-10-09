import { Link, useNavigate } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import { useDashboard, usePipelines } from "@/api/hooks";
import { useAssistant } from "@/assistant/AssistantContext";
import { useCurrentUser } from "@/app/currentUser";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { ErrorState } from "@/components/ui/States";
import { Skeleton } from "@/components/ui/Skeleton";
import { AssistantMark } from "@/assistant/AssistantChat";
import { ClassPlate } from "@/components/crm/ClassPlate";
import { PriorityBadge, StageBadge, TicketStageBadge } from "@/components/crm/Badges";
import { Money, OwnerChip, RecordLink, RelativeTime } from "@/components/crm/Values";
import { cn } from "@/lib/cn";
import { formatNumber } from "@/lib/format";
import { displayStageLabel, isLostStage, isWonStage } from "@/lib/stages";

export function Dashboard() {
  const navigate = useNavigate();
  const { user } = useCurrentUser();
  const assistant = useAssistant();
  const dealPipelines = usePipelines("deals");
  const ticketPipelines = usePipelines("tickets");
  const dash = useDashboard(dealPipelines.data, ticketPipelines.data);
  const today = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(new Date());

  const error = dealPipelines.error ?? ticketPipelines.error ?? dash.error;
  if (error) {
    return (
      <div className="flex flex-1 flex-col">
        <PageHeader title="Dashboard" meta={<span>{today}</span>} />
        <ErrorState
          error={error}
          onRetry={() => {
            void dealPipelines.refetch();
            void ticketPipelines.refetch();
            void dash.refetch();
          }}
          title="Could not load the overview"
        />
      </div>
    );
  }

  const d = dash.data;
  const openStages = d?.stageCounts.filter((s) => !isWonStage(s.stage) && !isLostStage(s.stage)) ?? [];
  const openDeals = openStages.reduce((a, s) => a + s.count, 0);
  const wonDeals = d?.stageCounts.filter((s) => isWonStage(s.stage)).reduce((a, s) => a + s.count, 0) ?? 0;
  const openTickets = d?.ticketStageCounts.filter((s) => !(s.stage.metadata?.isClosed === "true" || s.stage.metadata?.isClosed === true)).reduce((a, s) => a + s.count, 0) ?? 0;
  const maxStage = Math.max(1, ...(d?.stageCounts.map((s) => s.count) ?? [1]));
  const maxTicket = Math.max(1, ...(d?.ticketStageCounts.map((s) => s.count) ?? [1]));

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title={`Good ${greeting()}, ${user.name.split(" ")[0]}`}
        meta={<span>{today} · Brambilla Forniture</span>}
        actions={
          <Button variant="secondary" icon={<AssistantMark size={16} />} onClick={() => assistant.ask("Cosa devo fare oggi? Trattative in chiusura, ticket urgenti e clienti da richiamare.")}>
            What should I do today?
          </Button>
        }
      />

      <div className="grid gap-4 p-6">
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <Tile label="Companies" value={d?.totals.companies} to="/companies" loading={!d} />
          <Tile label="Contacts" value={d?.totals.contacts} to="/contacts" loading={!d} />
          <Tile label="Open deals" value={d ? openDeals : undefined} sub={d ? `${formatNumber(wonDeals)} won overall` : undefined} to="/deals" loading={!d} />
          <Tile label="Open tickets" value={d ? openTickets : undefined} sub={d ? `${formatNumber(d.totals.tickets)} overall` : undefined} to="/tickets" loading={!d} tone={openTickets > 0 ? "warn" : undefined} />
        </div>

        <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          <Card>
            <CardHeader title="Sales pipeline by stage" meta={d ? `${formatNumber(d.totals.deals)} deals in all pipelines` : undefined} actions={<Link to="/deals" className="text-[12px] font-medium text-gentian hover:underline">Open the board</Link>} />
            <CardBody>
              {!d ? (
                <div className="space-y-3">
                  {Array.from({ length: 7 }).map((_, i) => (
                    <Skeleton key={i} className="h-5 w-full" />
                  ))}
                </div>
              ) : (
                <ol className="space-y-2" aria-label="Deals per stage">
                  {d.stageCounts.map(({ stage, count }) => {
                    const closed = isWonStage(stage) || isLostStage(stage);
                    return (
                      <li key={stage.id} className="grid grid-cols-[120px_1fr_48px] items-center gap-3 text-[13px]">
                        <Link to={`/deals?pipeline=${d.sales?.id ?? "default"}`} className="truncate text-ink-2 hover:text-ink">
                          {displayStageLabel(stage)}
                        </Link>
                        <div className="h-4 rounded-r-sm bg-surface-3">
                          <div
                            className={cn("h-full rounded-r-sm", isWonStage(stage) ? "bg-good" : closed ? "bg-ink-3" : "bg-gentian")}
                            style={{ width: `${Math.max(count ? 2 : 0, (count / maxStage) * 100)}%` }}
                            role="img"
                            aria-label={`${displayStageLabel(stage)}: ${count} deals`}
                          />
                        </div>
                        <span className="text-right text-ink tnum">{formatNumber(count)}</span>
                      </li>
                    );
                  })}
                </ol>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Support queue" actions={<Link to="/tickets" className="text-[12px] font-medium text-gentian hover:underline">All tickets</Link>} />
            <CardBody>
              {!d ? (
                <div className="space-y-3">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <Skeleton key={i} className="h-5 w-full" />
                  ))}
                </div>
              ) : (
                <ol className="space-y-2" aria-label="Tickets per status">
                  {d.ticketStageCounts.map(({ stage, count }) => {
                    const closed = stage.metadata?.isClosed === "true" || stage.metadata?.isClosed === true;
                    return (
                      <li key={stage.id} className="grid grid-cols-[140px_1fr_48px] items-center gap-3 text-[13px]">
                        <Link to={`/tickets?scope=all&status=${stage.id}`} className="truncate text-ink-2 hover:text-ink">
                          {displayStageLabel(stage)}
                        </Link>
                        <div className="h-4 rounded-r-sm bg-surface-3">
                          <div className={cn("h-full rounded-r-sm", closed ? "bg-ink-3" : "bg-gentian")} style={{ width: `${Math.max(count ? 2 : 0, (count / maxTicket) * 100)}%` }} role="img" aria-label={`${displayStageLabel(stage)}: ${count} tickets`} />
                        </div>
                        <span className="text-right text-ink tnum">{formatNumber(count)}</span>
                      </li>
                    );
                  })}
                </ol>
              )}
            </CardBody>
          </Card>
        </div>

        <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          <Card>
            <CardHeader title="Recently updated deals" />
            {!d ? (
              <div className="space-y-3 p-4">
                {Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className="h-5 w-full" />
                ))}
              </div>
            ) : d.recentDeals.length === 0 ? (
              <p className="px-4 py-6 text-center text-[13px] text-ink-3">No deals yet.</p>
            ) : (
              <Table>
                <THead>
                  <TR>
                    <TH>Deal</TH>
                    <TH>Stage</TH>
                    <TH align="right">Amount</TH>
                    <TH>Owner</TH>
                    <TH align="right">Updated</TH>
                  </TR>
                </THead>
                <TBody>
                  {d.recentDeals.map((deal) => {
                    const stage = dealPipelines.data?.find((p) => p.id === (deal.properties.pipeline || "default"))?.stages.find((s) => s.id === deal.properties.dealstage);
                    return (
                      <TR key={deal.id} interactive onClick={() => navigate(`/deals/${deal.id}`)}>
                        <TD>
                          <RecordLink to={`/deals/${deal.id}`}>{deal.properties.dealname || "Untitled deal"}</RecordLink>
                        </TD>
                        <TD>
                          <StageBadge stage={stage} stageId={deal.properties.dealstage} size="sm" />
                        </TD>
                        <TD align="right" numeric>
                          <Money amount={deal.properties.amount} currency={deal.properties.deal_currency_code} />
                        </TD>
                        <TD>
                          <OwnerChip email={deal.properties.commerciale} size="xs" />
                        </TD>
                        <TD align="right" muted>
                          <RelativeTime value={deal.properties.hs_lastmodifieddate ?? deal.updatedAt} />
                        </TD>
                      </TR>
                    );
                  })}
                </TBody>
              </Table>
            )}
          </Card>

          <div className="grid gap-4">
            <Card>
              <CardHeader title="Top customers in 2025" actions={<Link to="/companies?sort=revenue" className="text-[12px] font-medium text-gentian hover:underline">All companies</Link>} />
              {!d ? (
                <div className="space-y-3 p-4">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <Skeleton key={i} className="h-5 w-full" />
                  ))}
                </div>
              ) : d.topCompanies.length === 0 ? (
                <p className="px-4 py-6 text-center text-[13px] text-ink-3">No revenue recorded for 2025 yet.</p>
              ) : (
                <ul className="divide-y divide-line">
                  {d.topCompanies.map((c) => (
                    <li key={c.id}>
                      <Link to={`/companies/${c.id}`} className="flex items-center gap-2.5 px-4 py-2 hover:bg-surface-2">
                        <ClassPlate value={c.properties.classe_cliente} size="sm" />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13px] font-medium text-ink">{c.properties.name}</span>
                          <span className="block truncate text-[12px] text-ink-3">{[c.properties.city, c.properties.state].filter(Boolean).join(", ")}</span>
                        </span>
                        <Money amount={c.properties.fatturato_2025} currency="EUR" className="text-[13px]" />
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Card>
              <CardHeader title="Latest tickets" />
              {!d ? (
                <div className="space-y-3 p-4">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <Skeleton key={i} className="h-5 w-full" />
                  ))}
                </div>
              ) : d.recentTickets.length === 0 ? (
                <p className="px-4 py-6 text-center text-[13px] text-ink-3">No tickets yet.</p>
              ) : (
                <ul className="divide-y divide-line">
                  {d.recentTickets.map((t) => {
                    const stage = ticketPipelines.data?.flatMap((p) => p.stages).find((s) => s.id === t.properties.hs_pipeline_stage);
                    return (
                      <li key={t.id}>
                        <Link to={`/tickets/${t.id}`} className="flex items-center gap-2.5 px-4 py-2 hover:bg-surface-2">
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-[13px] font-medium text-ink">{t.properties.subject}</span>
                            <span className="mt-0.5 flex items-center gap-1.5">
                              <TicketStageBadge stage={stage} stageId={t.properties.hs_pipeline_stage} size="sm" />
                              <PriorityBadge value={t.properties.hs_ticket_priority} size="sm" />
                            </span>
                          </span>
                          <RelativeTime value={t.properties.createdate} className="text-[12px] text-ink-3" />
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              )}
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "morning" : h < 18 ? "afternoon" : "evening";
}

function Tile({ label, value, sub, to, loading, tone }: { label: string; value: number | undefined; sub?: string; to: string; loading: boolean; tone?: "warn" }) {
  return (
    <Link to={to} className="group rounded-lg border border-line bg-surface px-4 py-3 transition-colors hover:border-line-strong">
      <div className="flex items-center justify-between text-[12.5px] text-ink-2">
        {label}
        <ArrowUpRight className="size-3.5 text-ink-3 opacity-0 transition-opacity group-hover:opacity-100" aria-hidden />
      </div>
      {loading ? (
        <Skeleton className="mt-1.5 h-7 w-20" />
      ) : (
        <div className={cn("mt-0.5 font-wide text-[26px] font-semibold tracking-tight pnum", tone === "warn" && value ? "text-warn" : "text-ink")}>{formatNumber(value)}</div>
      )}
      {sub && !loading ? <div className="text-[12px] text-ink-3">{sub}</div> : <div className="h-[18px]" />}
    </Link>
  );
}
