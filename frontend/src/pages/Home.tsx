import { useEffect } from "react";
import { Link } from "react-router-dom";
import { motion } from "motion/react";
import { ArrowUpRight } from "lucide-react";
import { useDashboard, usePipelines } from "@/api/hooks";
import { useAssistant } from "@/assistant/AssistantContext";
import { AssistantChat, Composer, SuggestionChips } from "@/assistant/AssistantChat";
import { AssistantMark } from "@/assistant/AssistantMark";
import { useCurrentUser } from "@/app/currentUser";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/States";
import { Skeleton } from "@/components/ui/Skeleton";
import { CountUp, GrowBar, Rise, staggerChild, staggerParent } from "@/components/motion/primitives";
import { cn } from "@/lib/cn";
import { formatNumber } from "@/lib/format";
import { displayStageLabel, isClosedTicketStage, isLostStage, isWonStage } from "@/lib/stages";

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
        <div className={cn("mx-auto w-full max-w-6xl px-4 sm:px-6", inConversation ? "py-4" : "py-8 md:py-14")}>
          {inConversation ? (
            <div className="flex h-[min(72vh,760px)] flex-col overflow-hidden rounded-lg border border-line bg-surface shadow-card">
              <AssistantChat variant="home" />
            </div>
          ) : (
            <div className="grid items-center gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
              <Rise className="min-w-0">
                <p className="text-[13px] text-ink-2">{today}</p>
                <h1 className="mt-3 font-wide text-[40px] leading-[1.02] font-semibold tracking-[-0.03em] text-ink md:text-[52px]">
                  Good {greeting()},
                  <br />
                  {user.name.split(" ")[0]}.
                </h1>
                <p className="mt-4 max-w-sm text-[14px] leading-relaxed text-ink-2">Ask in plain words. Answers come in Italian, from the same records as every page.</p>
              </Rise>
              <Rise delay={0.08} className="min-w-0">
                <div className="rounded-[22px] border border-line bg-surface p-4 text-ink shadow-pop">
                  <div className="mb-3 flex items-center gap-2.5 px-1">
                    <AssistantMark size={26} />
                    <span className="text-[14px] font-semibold">Ask the CRM</span>
                  </div>
                  <SuggestionChips limit={4} />
                  <Composer size="lg" autoFocus className="mt-3" />
                </div>
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
  const dealPipelines = usePipelines("deals");
  const ticketPipelines = usePipelines("tickets");
  const dash = useDashboard(dealPipelines.data, ticketPipelines.data);

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

  return (
    <div className="mx-auto grid w-full min-w-0 max-w-6xl gap-4 p-4 sm:p-6">
      <motion.div variants={staggerParent} initial="hidden" animate="show" className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        <Tile label="Companies" value={d?.totals.companies} to="/companies" loading={!d} />
        <Tile label="Contacts" value={d?.totals.contacts} to="/contacts" loading={!d} />
        <Tile label="Open deals" value={d ? openDeals : undefined} sub={d ? `${formatNumber(wonDeals)} won overall` : undefined} to="/deals" loading={!d} />
        <Tile label="Open tickets" value={d ? openTickets : undefined} sub={d ? `${formatNumber(d.totals.tickets)} overall` : undefined} to="/tickets" loading={!d} tone={openTickets > 0 ? "warn" : undefined} />
              </motion.div>

      <motion.div variants={staggerParent} initial="hidden" animate="show" className="grid gap-4 lg:grid-cols-2">
        <motion.div variants={staggerChild}><Card className="min-w-0">
          <CardHeader title="Sales pipeline by stage" meta={d ? `${formatNumber(d.totals.deals)} deals in all pipelines` : undefined} actions={<Link to="/deals" className="text-[12px] font-medium text-gentian hover:underline">View board</Link>} />
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
        </Card></motion.div>

        <motion.div variants={staggerChild}><Card className="min-w-0">
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
        </Card></motion.div>
      </motion.div>

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




function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "morning" : h < 18 ? "afternoon" : "evening";
}
