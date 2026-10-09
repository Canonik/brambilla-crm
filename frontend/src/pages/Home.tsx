import { useEffect, useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import { ArrowUpRight, Kanban, LifeBuoy } from "lucide-react";
import * as api from "@/api/endpoints";
import { useDashboard, useDormantCompanies, usePipelines, useTickets } from "@/api/hooks";
import type { Ticket } from "@/api/types";
import { useAssistant } from "@/assistant/AssistantContext";
import { AssistantChat, Composer, SuggestionChips } from "@/assistant/AssistantChat";
import { AssistantMark } from "@/assistant/AssistantMark";
import { useCurrentUser } from "@/app/currentUser";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { ErrorState } from "@/components/ui/States";
import { Skeleton } from "@/components/ui/Skeleton";
import { ClassPlate } from "@/components/crm/ClassPlate";
import { PriorityBadge, StageBadge, TicketStageBadge } from "@/components/crm/Badges";
import { DateText, Money, OwnerChip, RecordLink, RelativeTime } from "@/components/crm/Values";
import { CountUp, GrowBar, Rise, staggerChild, staggerParent } from "@/components/motion/primitives";
import { cn } from "@/lib/cn";
import { formatNumber } from "@/lib/format";
import { displayStageLabel, isClosedTicketStage, isLostStage, isWonStage, priorityMeta } from "@/lib/stages";

// The home is the assistant's workspace: a question first, then the pulse of
// the CRM underneath. Once a conversation starts it takes the hero's place.

export function Home() {
  const { user } = useCurrentUser();
  const { messages, setOpen } = useAssistant();
  useEffect(() => setOpen(false), [setOpen]);
  const inConversation = messages.length > 0;
  const today = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(new Date());

  return (
    <div className="flex flex-1 flex-col">
      <section className="border-b border-line bg-surface" aria-label="Assistant">
        <div className={cn("mx-auto w-full max-w-6xl px-4 sm:px-6", inConversation ? "py-4" : "py-8 md:py-12")}>
          {inConversation ? (
            <div className="flex h-[min(72vh,760px)] flex-col overflow-hidden rounded-lg border border-line bg-surface shadow-card">
              <AssistantChat variant="home" />
            </div>
          ) : (
            <div className="mx-auto max-w-3xl">
              <Rise>
                <p className="text-[13px] text-ink-2">
                  {today} · working as <span className="text-ink">{user.name}</span>
                </p>
                <h1 className="mt-3 font-wide text-[30px] leading-[1.05] font-semibold tracking-tight text-ink md:text-[38px]">
                  What do you need from the CRM, {user.name.split(" ")[0]}?
                </h1>
                <p className="mt-3 max-w-xl text-[14px] leading-relaxed text-ink-2">
                  Ask in plain words. The assistant works on the same companies, deals and tickets as the pages, shows the records it touched, and answers in Italian.
                </p>
              </Rise>
              <Rise delay={0.08} className="mt-6">
                <Composer size="lg" autoFocus />
              </Rise>
              <Rise delay={0.16} className="mt-5">
                <SuggestionChips />
              </Rise>
            </div>
          )}
        </div>
      </section>
      <Pulse />
    </div>
  );
}

function Pulse() {
  const navigate = useNavigate();
  const { user } = useCurrentUser();
  const dealPipelines = usePipelines("deals");
  const ticketPipelines = usePipelines("tickets");
  const dash = useDashboard(dealPipelines.data, ticketPipelines.data);
  const dormant = useDormantCompanies();

  const error = dealPipelines.error ?? ticketPipelines.error ?? dash.error;
  if (error) {
    return (
      <ErrorState
        error={error}
        onRetry={() => {
          void dealPipelines.refetch();
          void ticketPipelines.refetch();
          void dash.refetch();
        }}
        title="Could not load the overview"
      />
    );
  }

  const d = dash.data;
  const openStages = d?.stageCounts.filter((s) => !isWonStage(s.stage) && !isLostStage(s.stage)) ?? [];
  const openDeals = openStages.reduce((a, s) => a + s.count, 0);
  const wonDeals = d?.stageCounts.filter((s) => isWonStage(s.stage)).reduce((a, s) => a + s.count, 0) ?? 0;
  const openTickets = d?.ticketStageCounts.filter((s) => !isClosedTicketStage(s.stage)).reduce((a, s) => a + s.count, 0) ?? 0;
  const maxStage = Math.max(1, ...(d?.stageCounts.map((s) => s.count) ?? [1]));
  const maxTicket = Math.max(1, ...(d?.ticketStageCounts.map((s) => s.count) ?? [1]));
  const dormantTotal = dormant.data?.pages[0]?.total ?? (dormant.data && !dormant.hasNextPage ? dormant.data.pages.flatMap((p) => p.companies).length : undefined);

  return (
    <div className="mx-auto grid w-full max-w-6xl gap-4 p-4 sm:p-6">
      <motion.div variants={staggerParent} initial="hidden" animate="show" className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <Tile label="Companies" value={d?.totals.companies} to="/companies" loading={!d} />
        <Tile label="Contacts" value={d?.totals.contacts} to="/contacts" loading={!d} />
        <Tile label="Open deals" value={d ? openDeals : undefined} sub={d ? `${formatNumber(wonDeals)} won overall` : undefined} to="/deals" loading={!d} />
        <Tile label="Open tickets" value={d ? openTickets : undefined} sub={d ? `${formatNumber(d.totals.tickets)} overall` : undefined} to="/tickets" loading={!d} tone={openTickets > 0 ? "warn" : undefined} />
        <Tile label="Dormant customers" value={dormantTotal} sub={dormantTotal !== undefined ? "won before, silent in 2025" : undefined} to="/dormant" loading={dormant.isPending} />
      </motion.div>

      <div className="grid gap-4 lg:grid-cols-2">
        <MyTickets user={user.email} closedStageIds={ticketPipelines.data?.flatMap((p) => p.stages).filter((s) => isClosedTicketStage(s)).map((s) => s.id) ?? []} />
        <DealsToClose user={user.email} />
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Card className="min-w-0">
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
                {d.stageCounts.map(({ stage, count }, i) => {
                  const closed = isWonStage(stage) || isLostStage(stage);
                  return (
                    <li key={stage.id} className="grid grid-cols-[110px_1fr_52px] items-center gap-3 text-[13px] sm:grid-cols-[130px_1fr_56px]">
                      <Link to={`/deals?pipeline=${d.sales?.id ?? "default"}`} className="truncate text-ink-2 hover:text-ink">
                        {displayStageLabel(stage)}
                      </Link>
                      <div className="h-4 rounded-r-sm bg-surface-3" role="img" aria-label={`${displayStageLabel(stage)}: ${count} deals`}>
                        <GrowBar percent={Math.max(count ? 2 : 0, (count / maxStage) * 100)} delay={i * 0.04} className={cn("h-full rounded-r-sm", isWonStage(stage) ? "bg-good" : closed ? "bg-ink-3" : "bg-gentian")} />
                      </div>
                      <span className="text-right text-ink tnum">{formatNumber(count)}</span>
                    </li>
                  );
                })}
              </ol>
            )}
          </CardBody>
        </Card>

        <Card className="min-w-0">
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
                {d.ticketStageCounts.map(({ stage, count }, i) => {
                  const closed = isClosedTicketStage(stage);
                  return (
                    <li key={stage.id} className="grid grid-cols-[110px_1fr_52px] items-center gap-3 text-[13px] sm:grid-cols-[150px_1fr_56px]">
                      <Link to={`/tickets?scope=all&status=${stage.id}`} className="truncate text-ink-2 hover:text-ink">
                        {displayStageLabel(stage)}
                      </Link>
                      <div className="h-4 rounded-r-sm bg-surface-3" role="img" aria-label={`${displayStageLabel(stage)}: ${count} tickets`}>
                        <GrowBar percent={Math.max(count ? 2 : 0, (count / maxTicket) * 100)} delay={i * 0.04} className={cn("h-full rounded-r-sm", closed ? "bg-ink-3" : "bg-gentian")} />
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
        <Card className="min-w-0">
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

        <Card className="min-w-0">
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
      </div>
    </div>
  );
}

function Tile({ label, value, sub, to, loading, tone }: { label: string; value: number | undefined; sub?: string; to: string; loading: boolean; tone?: "warn" }) {
  return (
    <motion.div variants={staggerChild} className="min-w-0">
      <Link to={to} className="group block rounded-lg border border-line bg-surface px-4 py-3 transition-colors hover:border-line-strong">
        <div className="flex items-center justify-between text-[12.5px] text-ink-2">
          <span className="truncate">{label}</span>
          <ArrowUpRight className="size-3.5 shrink-0 text-ink-3 opacity-0 transition-opacity group-hover:opacity-100" aria-hidden />
        </div>
        {loading || value === undefined ? (
          <Skeleton className="mt-1.5 h-7 w-20" />
        ) : (
          <div className={cn("mt-0.5 font-wide text-[26px] font-semibold tracking-tight pnum", tone === "warn" && value ? "text-warn" : "text-ink")}>
            <CountUp value={value} format={formatNumber} />
          </div>
        )}
        {sub && !loading ? <div className="truncate text-[12px] text-ink-3">{sub}</div> : <div className="h-[18px]" />}
      </Link>
    </motion.div>
  );
}

function AskRow({ prompt, label = "Ask" }: { prompt: string; label?: string }) {
  const { send } = useAssistant();
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        document.querySelector("main")?.scrollTo({ top: 0, behavior: "smooth" });
        void send(prompt);
      }}
      className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md border border-line bg-surface px-2 text-[12px] font-medium text-ink-2 transition-colors hover:border-gentian-line hover:bg-gentian-soft hover:text-gentian"
    >
      <AssistantMark size={14} />
      {label}
    </button>
  );
}

function MyTickets({ user, closedStageIds }: { user: string; closedStageIds: string[] }) {
  const navigate = useNavigate();
  const pipelines = usePipelines("tickets");
  const closedKey = closedStageIds.join(",");
  const params = useMemo(() => ({ owner: user, openOnly: true, closedStageIds: closedKey ? closedKey.split(",") : [], limit: 50 }), [user, closedKey]);
  const query = useTickets(params);
  const rows = useMemo(() => {
    const list: Ticket[] = query.data?.pages.flatMap((p) => p.results) ?? [];
    return list
      .slice()
      .sort((a, b) => priorityMeta(b.properties.hs_ticket_priority).rank - priorityMeta(a.properties.hs_ticket_priority).rank || (Date.parse(b.properties.createdate ?? "") || 0) - (Date.parse(a.properties.createdate ?? "") || 0))
      .slice(0, 5);
  }, [query.data]);
  const total = query.data?.pages[0]?.total;
  const stageOf = (id: string | null | undefined) => pipelines.data?.flatMap((p) => p.stages).find((s) => s.id === id);
  return (
    <Card className="min-w-0">
      <CardHeader title="Your open tickets" meta={total !== undefined ? `${formatNumber(total)}` : undefined} actions={<Link to="/tickets?mine=1" className="text-[12px] font-medium text-gentian hover:underline">Assigned to me</Link>} />
      {query.isPending ? (
        <div className="space-y-3 p-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-5 w-full" />
          ))}
        </div>
      ) : query.isError ? (
        <ErrorState compact error={query.error} onRetry={() => query.refetch()} title="Could not load your tickets" />
      ) : rows.length === 0 ? (
        <div className="flex flex-col items-center gap-2 px-4 py-8 text-center">
          <LifeBuoy className="size-5 text-ink-3" aria-hidden />
          <p className="text-[13px] text-ink-2">Nothing open is assigned to you.</p>
          <AskRow prompt="Quali ticket urgenti sono ancora aperti e a chi sono assegnati?" label="Ask who has urgent tickets" />
        </div>
      ) : (
        <ul className="divide-y divide-line">
          {rows.map((t) => (
            <li key={t.id} className="flex cursor-pointer items-center gap-3 px-4 py-2 hover:bg-surface-2" onClick={() => navigate(`/tickets/${t.id}`)} role="link" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && navigate(`/tickets/${t.id}`)}>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] font-medium text-ink">{t.properties.subject || "Untitled ticket"}</span>
                <span className="mt-0.5 flex flex-wrap items-center gap-1.5">
                  <PriorityBadge value={t.properties.hs_ticket_priority} size="sm" />
                  <TicketStageBadge stage={stageOf(t.properties.hs_pipeline_stage)} stageId={t.properties.hs_pipeline_stage} size="sm" />
                  <RelativeTime value={t.properties.createdate} className="text-[11.5px] text-ink-3" />
                </span>
              </span>
              <AskRow prompt={`Riassumi il ticket "${t.properties.subject ?? t.id}" e proponi la prossima azione.`} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function DealsToClose({ user }: { user: string }) {
  const navigate = useNavigate();
  const mine = useQuery({ queryKey: ["home", "deals-to-close", user], queryFn: () => api.listDeals({ pipeline: "default", stage: "contractsent", owner: user, limit: 20 }), staleTime: 60_000 });
  const all = useQuery({ queryKey: ["home", "deals-to-close", "all"], queryFn: () => api.listDeals({ pipeline: "default", stage: "contractsent", limit: 20 }), staleTime: 60_000, enabled: mine.isSuccess && (mine.data?.results?.length ?? 0) === 0 });
  const own = (mine.data?.results?.length ?? 0) > 0;
  const source = own ? mine : all;
  const rows = (source.data?.results ?? []).slice().sort((a, b) => (Date.parse(a.properties.closedate ?? "") || Infinity) - (Date.parse(b.properties.closedate ?? "") || Infinity)).slice(0, 5);
  return (
    <Card className="min-w-0">
      <CardHeader title={own ? "Your deals with a contract out" : "Deals with a contract out"} meta={source.data?.total !== undefined ? `${formatNumber(source.data.total)}` : undefined} actions={<Link to="/deals" className="text-[12px] font-medium text-gentian hover:underline">Board</Link>} />
      {mine.isPending || (all.isPending && all.fetchStatus !== "idle") ? (
        <div className="space-y-3 p-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-5 w-full" />
          ))}
        </div>
      ) : source.isError ? (
        <ErrorState compact error={source.error} onRetry={() => source.refetch()} title="Could not load the deals" />
      ) : rows.length === 0 ? (
        <div className="flex flex-col items-center gap-2 px-4 py-8 text-center">
          <Kanban className="size-5 text-ink-3" aria-hidden />
          <p className="text-[13px] text-ink-2">No contract is waiting for a signature.</p>
        </div>
      ) : (
        <ul className="divide-y divide-line">
          {rows.map((d) => (
            <li key={d.id} className="flex cursor-pointer items-center gap-3 px-4 py-2 hover:bg-surface-2" onClick={() => navigate(`/deals/${d.id}`)} role="link" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && navigate(`/deals/${d.id}`)}>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] font-medium text-ink">{d.properties.dealname || "Untitled deal"}</span>
                <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11.5px] text-ink-3">
                  <Money amount={d.properties.amount} currency={d.properties.deal_currency_code} className="text-ink-2" />
                  <span>
                    close <DateText value={d.properties.closedate} />
                  </span>
                  {!own ? <OwnerChip email={d.properties.commerciale} size="xs" /> : null}
                </span>
              </span>
              <AskRow prompt={`Riassumi la trattativa "${d.properties.dealname ?? d.id}" e dimmi cosa manca per chiuderla.`} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
