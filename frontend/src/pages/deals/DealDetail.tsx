import { useEffect, useMemo, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Check, MessageSquareText } from "lucide-react";
import { useActivities, useDealPage, useMoveDeal, usePipelines } from "@/api/hooks";
import { useAssistant } from "@/assistant/AssistantContext";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Avatar } from "@/components/ui/Avatar";
import { NativeSelect } from "@/components/ui/Input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { Skeleton, SkeletonBlock } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toaster";
import { ClassPlate } from "@/components/crm/ClassPlate";
import { PriorityBadge, StageBadge, TicketStageBadge } from "@/components/crm/Badges";
import { DateText, Money, OwnerChip, PropertyList, RecordLink } from "@/components/crm/Values";
import { ActivityFeed, NoteComposer } from "@/components/crm/ActivityFeed";
import { cn } from "@/lib/cn";
import { formatMoney, formatNumber, formatPercent, fullName, toNumber } from "@/lib/format";
import { displayPipelineLabel, displayStageLabel, isLostStage, isWonStage } from "@/lib/stages";

export function DealDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const page = useDealPage(id);
  const pipelines = usePipelines("deals");
  const ticketPipelines = usePipelines("tickets");
  const assistant = useAssistant();
  const toast = useToast();
  const targets = useMemo(() => [{ type: "deals" as const, ids: id ? [id] : [] }], [id]);
  const activities = useActivities(`deal:${id}`, targets, page.isSuccess);
  const pipeline = pipelines.data?.find((p) => p.id === (page.data?.deal.properties.pipeline || "default"));
  const move = useMoveDeal(pipeline);
  // The CRM opens the supply kickoff ticket (R10) and the callback task (R11)
  // asynchronously after a stage change; poll briefly so they show up.
  const timers = useRef<number[]>([]);
  const scheduleRefetch = () => {
    timers.current.forEach((t) => window.clearTimeout(t));
    timers.current = [1500, 4000, 9000].map((ms) =>
      window.setTimeout(() => {
        void page.refetch();
        void activities.refetch();
      }, ms),
    );
  };
  useEffect(() => () => timers.current.forEach((t) => window.clearTimeout(t)), []);

  if (page.isPending) {
    return (
      <div className="flex flex-1 flex-col">
        <PageHeader title={<Skeleton className="h-6 w-72" />} crumbs={[{ label: "Deals", to: "/deals" }, { label: "Loading" }]} />
        <div className="grid gap-4 p-6 lg:grid-cols-3">
          <SkeletonBlock lines={6} className="lg:col-span-2" />
          <SkeletonBlock lines={8} />
        </div>
      </div>
    );
  }
  if (page.isError || !page.data) {
    return (
      <div className="flex flex-1 flex-col">
        <PageHeader title="Deal" crumbs={[{ label: "Deals", to: "/deals" }, { label: "Not found" }]} />
        <ErrorState error={page.error} onRetry={() => page.refetch()} title="Could not load this deal" />
      </div>
    );
  }

  const { deal, companies, contacts, lineItems, tickets } = page.data;
  const p = deal.properties;
  const title = p.dealname || "Untitled deal";
  const stage = pipeline?.stages.find((s) => s.id === p.dealstage);
  const stageIndex = pipeline?.stages.findIndex((s) => s.id === p.dealstage) ?? -1;
  const company = companies[0];
  const lineTotal = lineItems.reduce((acc, li) => acc + (toNumber(li.properties.amount) ?? 0), 0);

  const changeStage = async (toStage: string) => {
    if (!toStage || toStage === p.dealstage) return;
    try {
      await move.mutateAsync({ deal, toStage });
      toast.success(`Moved to ${displayStageLabel(pipeline?.stages.find((s) => s.id === toStage))}`);
      scheduleRefetch();
    } catch (err) {
      toast.error("Could not change the stage", err instanceof Error ? err.message : undefined);
    }
  };

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        crumbs={[{ label: "Deals", to: `/deals?pipeline=${encodeURIComponent(p.pipeline || "default")}` }, { label: title }]}
        title={title}
        eyebrow={pipeline ? `${displayPipelineLabel(pipeline)} pipeline` : undefined}
        meta={
          <>
            <StageBadge stage={stage} stageId={p.dealstage} />
            <Money amount={p.amount} currency={p.deal_currency_code} className="font-semibold text-ink" />
            {p.closedate ? (
              <span>
                {isWonStage(stage) || isLostStage(stage) ? "Closed" : "Expected close"} <DateText value={p.closedate} />
              </span>
            ) : null}
            <OwnerChip email={p.commerciale} size="xs" />
          </>
        }
        actions={
          <>
            {pipeline ? (
              <NativeSelect
                aria-label="Move to stage"
                value={p.dealstage ?? ""}
                onChange={(e) => void changeStage(e.target.value)}
                options={pipeline.stages.map((s) => ({ value: s.id, label: displayStageLabel(s) }))}
                className="w-48"
                disabled={move.isPending}
              />
            ) : null}
            <Button variant="secondary" icon={<MessageSquareText className="size-4" />} onClick={() => assistant.ask(`Riassumi la trattativa "${title}"${company ? ` di ${company.properties.name}` : ""} e dimmi cosa manca per chiuderla.`)}>
              Ask about this deal
            </Button>
          </>
        }
      />

      <div className="grid flex-1 gap-4 p-6 lg:grid-cols-[minmax(0,2fr)_minmax(280px,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          {pipeline ? (
            <Card>
              <CardBody className="p-3">
                <ol className="flex flex-wrap gap-1" aria-label="Stages">
                  {pipeline.stages.map((s, i) => {
                    const done = stageIndex >= 0 && i < stageIndex && !isLostStage(stage);
                    const current = s.id === p.dealstage;
                    const lostStep = isLostStage(s);
                    return (
                      <li key={s.id} className="flex-1 basis-24">
                        <button
                          type="button"
                          onClick={() => void changeStage(s.id)}
                          disabled={move.isPending || current}
                          className={cn(
                            "flex w-full items-center gap-1.5 rounded-sm border px-2 py-1.5 text-left text-[12px] font-medium transition-colors",
                            current
                              ? isWonStage(s)
                                ? "border-good bg-good-soft text-good"
                                : lostStep
                                  ? "border-ink-3 bg-surface-3 text-ink"
                                  : "border-gentian bg-gentian-soft text-gentian"
                              : done
                                ? "border-line bg-surface-2 text-ink-2"
                                : "border-line bg-surface text-ink-2 hover:border-line-strong hover:text-ink",
                          )}
                          aria-current={current ? "step" : undefined}
                        >
                          <span className={cn("inline-flex size-4 shrink-0 items-center justify-center rounded-full border text-[10px]", current ? "border-current" : done ? "border-ink-3 bg-ink-3 text-white" : "border-line-strong")}>
                            {done ? <Check className="size-2.5" /> : i + 1}
                          </span>
                          <span className="truncate">{displayStageLabel(s)}</span>
                        </button>
                      </li>
                    );
                  })}
                </ol>
              </CardBody>
            </Card>
          ) : null}

          <Card>
            <CardHeader title="Line items" meta={lineItems.length ? `${lineItems.length}` : undefined} />
            {lineItems.length === 0 ? (
              <EmptyState compact title="No line items" description="Deals migrated with quote lines show their products here; the deal amount is their total." />
            ) : (
              <Table>
                <THead>
                  <TR>
                    <TH>Product</TH>
                    <TH>Code</TH>
                    <TH align="right">Qty</TH>
                    <TH align="right">Unit price</TH>
                    <TH align="right">Discount</TH>
                    <TH align="right">Total</TH>
                  </TR>
                </THead>
                <TBody>
                  {lineItems.map((li) => (
                    <TR key={li.id}>
                      <TD className="font-medium">{li.properties.name || "Unnamed item"}</TD>
                      <TD muted numeric>{li.properties.hs_sku || "–"}</TD>
                      <TD align="right" numeric>{formatNumber(li.properties.quantity)}</TD>
                      <TD align="right" numeric>{formatMoney(li.properties.price, "EUR")}</TD>
                      <TD align="right" numeric muted>{formatPercent(li.properties.hs_discount_percentage ?? "0")}</TD>
                      <TD align="right" numeric className="font-medium">{formatMoney(li.properties.amount, "EUR")}</TD>
                    </TR>
                  ))}
                  <TR>
                    <TD colSpan={5} align="right" className="border-b-0 text-ink-2">Total</TD>
                    <TD align="right" numeric className="border-b-0 font-semibold">{formatMoney(lineTotal, "EUR")}</TD>
                  </TR>
                </TBody>
              </Table>
            )}
          </Card>

          <Card>
            <CardHeader title="History" meta={activities.data?.length || undefined} />
            <NoteComposer target={{ type: "deals", id: deal.id }} />
            <ActivityFeed activities={activities.data} isLoading={activities.isPending && activities.fetchStatus !== "idle"} error={activities.error} onRetry={() => activities.refetch()} />
          </Card>
        </div>

        <div className="flex min-w-0 flex-col gap-4">
          <Card>
            <CardHeader title="Company" />
            <CardBody className="p-2">
              {company ? (
                <RecordLink to={`/companies/${company.id}`} className="flex items-center gap-2.5 rounded-md px-2 py-2 font-normal hover:bg-surface-2 hover:no-underline">
                  <Avatar name={company.properties.name} size="md" square />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-medium text-ink">{company.properties.name}</span>
                    <span className="block truncate text-[12px] text-ink-3">{[company.properties.city, company.properties.state].filter(Boolean).join(", ") || company.properties.domain}</span>
                  </span>
                  <ClassPlate value={company.properties.classe_cliente} size="sm" />
                </RecordLink>
              ) : (
                <p className="px-2 py-1 text-[13px] text-ink-3">No company linked.</p>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Contacts" meta={contacts.length || undefined} />
            <CardBody className="p-2">
              {contacts.length === 0 ? (
                <p className="px-2 py-1 text-[13px] text-ink-3">No contacts linked.</p>
              ) : (
                <ul className="divide-y divide-line">
                  {contacts.map((c) => (
                    <li key={c.id}>
                      <RecordLink to={`/contacts/${c.id}`} className="flex items-center gap-2.5 rounded-md px-2 py-1.5 font-normal hover:bg-surface-2 hover:no-underline">
                        <Avatar name={fullName(c.properties.firstname, c.properties.lastname)} size="sm" />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13px] font-medium text-ink">{fullName(c.properties.firstname, c.properties.lastname)}</span>
                          <span className="block truncate text-[12px] text-ink-3">{c.properties.email || c.properties.jobtitle}</span>
                        </span>
                      </RecordLink>
                    </li>
                  ))}
                </ul>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Tickets" meta={tickets.length || undefined} />
            <CardBody className="p-2">
              {tickets.length === 0 ? (
                <p className="px-2 py-1 text-[13px] text-ink-3">No tickets linked. Winning a sales deal opens a supply kickoff ticket automatically.</p>
              ) : (
                <ul className="divide-y divide-line">
                  {tickets.map((t) => {
                    const ts = ticketPipelines.data?.flatMap((pl) => pl.stages).find((s) => s.id === t.properties.hs_pipeline_stage);
                    const automatic = (t.properties.subject ?? "").startsWith("Avvio fornitura - ");
                    return (
                      <li key={t.id} className="px-2 py-2">
                        <RecordLink to={`/tickets/${t.id}`} className="block truncate text-[13px]">{t.properties.subject}</RecordLink>
                        {automatic ? <div className="mt-0.5 text-[11.5px] text-good">Opened by the CRM when the deal was won</div> : null}
                        <div className="mt-1 flex items-center gap-1.5">
                          <TicketStageBadge stage={ts} stageId={t.properties.hs_pipeline_stage} size="sm" />
                          <PriorityBadge value={t.properties.hs_ticket_priority} size="sm" />
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Details" />
            <CardBody>
              <PropertyList
                items={[
                  { label: "Amount", value: <Money amount={p.amount} currency={p.deal_currency_code} /> },
                  { label: "Currency", value: p.amount ? p.deal_currency_code || "EUR" : null },
                  { label: "Pipeline", value: pipeline ? displayPipelineLabel(pipeline) : p.pipeline },
                  { label: "Stage", value: <StageBadge stage={stage} stageId={p.dealstage} size="sm" /> },
                  { label: "Close date", value: <DateText value={p.closedate} /> },
                  { label: "Owner", value: <OwnerChip email={p.commerciale} size="xs" /> },
                  { label: "Description", value: p.description },
                  { label: "Legacy id", value: p.id_legacy ? <span className="tnum">{p.id_legacy}</span> : null },
                  { label: "Created", value: <DateText value={p.createdate ?? deal.createdAt} /> },
                  { label: "Updated", value: <DateText value={p.hs_lastmodifieddate ?? deal.updatedAt} withTime /> },
                ]}
              />
            </CardBody>
          </Card>
          <Button variant="ghost" size="sm" className="self-start" onClick={() => navigate(`/deals?pipeline=${encodeURIComponent(p.pipeline || "default")}`)}>
            Back to the board
          </Button>
        </div>
      </div>
    </div>
  );
}
