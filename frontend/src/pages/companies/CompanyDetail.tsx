import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ExternalLink, MessageSquareText } from "lucide-react";
import { useActivities, useCompanyPage, usePipelines } from "@/api/hooks";
import type { Deal, Ticket } from "@/api/types";
import { useAssistant } from "@/assistant/AssistantContext";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Avatar } from "@/components/ui/Avatar";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { Skeleton, SkeletonBlock } from "@/components/ui/Skeleton";
import { ClassPlate } from "@/components/crm/ClassPlate";
import { ClassScale } from "@/components/crm/ClassScale";
import { LifecycleBadge, PriorityBadge, StageBadge, TicketStageBadge } from "@/components/crm/Badges";
import { DateText, Money, OwnerChip, PropertyList, RecordLink, RelativeTime } from "@/components/crm/Values";
import { ActivityFeed, NoteComposer } from "@/components/crm/ActivityFeed";
import { formatMoney, fullName, toNumber } from "@/lib/format";
import { isClosedStage, isClosedTicketStage, isWonStage } from "@/lib/stages";
import { sumEur } from "@/lib/money";
import { userName } from "@/api/users";

export function CompanyDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const page = useCompanyPage(id);
  const dealPipelines = usePipelines("deals");
  const ticketPipelines = usePipelines("tickets");
  const assistant = useAssistant();
  const [historyFilter, setHistoryFilter] = useState<"all" | "notes" | "calls" | "emails" | "meetings" | "tasks">("all");

  const contacts = page.data?.contacts ?? [];
  const deals = page.data?.deals ?? [];
  const tickets = page.data?.tickets ?? [];

  const activityTargets = useMemo(
    () => [
      { type: "companies" as const, ids: id ? [id] : [] },
      { type: "contacts" as const, ids: contacts.map((c) => c.id) },
      { type: "deals" as const, ids: deals.map((d) => d.id) },
    ],
    [id, contacts, deals],
  );
  const activities = useActivities(`company:${id}:${contacts.length}:${deals.length}`, activityTargets, page.isSuccess);

  const stageOf = (d: Deal) =>
    dealPipelines.data?.find((p) => p.id === (d.properties.pipeline || "default"))?.stages.find((s) => s.id === d.properties.dealstage);
  const ticketStageOf = (t: Ticket) =>
    ticketPipelines.data?.flatMap((p) => p.stages).find((s) => s.id === t.properties.hs_pipeline_stage);

  if (page.isPending) {
    return (
      <div className="flex flex-1 flex-col">
        <PageHeader title={<Skeleton className="h-6 w-64" />} crumbs={[{ label: "Companies", to: "/companies" }, { label: "Loading" }]} />
        <div className="grid gap-4 p-6 lg:grid-cols-3">
          <SkeletonBlock lines={5} className="lg:col-span-2" />
          <SkeletonBlock lines={8} />
        </div>
      </div>
    );
  }
  if (page.isError || !page.data) {
    return (
      <div className="flex flex-1 flex-col">
        <PageHeader title="Company" crumbs={[{ label: "Companies", to: "/companies" }, { label: "Not found" }]} />
        <ErrorState error={page.error} onRetry={() => page.refetch()} title="Could not load this company" />
      </div>
    );
  }

  const { company } = page.data;
  const p = company.properties;
  const name = p.name || "Unnamed company";
  const revenue = toNumber(p.fatturato_2025) ?? 0;
  const openDeals = deals.filter((d) => !isClosedStage(stageOf(d)));
  const wonDeals = deals.filter((d) => isWonStage(stageOf(d)));
  const openTickets = tickets.filter((t) => {
    const s = ticketStageOf(t);
    return s ? !isClosedTicketStage(s) : !t.properties.closed_date;
  });
  const pipelineValue = sumEur(openDeals.map((d) => ({ amount: d.properties.amount, currency: d.properties.deal_currency_code })));
  const owners = Array.from(new Set([...deals.map((d) => d.properties.commerciale), ...tickets.map((t) => t.properties.assegnatario)].filter(Boolean))) as string[];
  const domains = [p.domain, ...(p.hs_additional_domains ?? "").split(";")].map((d) => d?.trim()).filter(Boolean) as string[];

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        crumbs={[{ label: "Companies", to: "/companies" }, { label: name }]}
        leading={<Avatar name={name} size="lg" square />}
        title={name}
        meta={
          <>
            {domains[0] ? (
              <a href={`https://${domains[0]}`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-gentian hover:underline">
                {domains[0]}
                <ExternalLink className="size-3" aria-hidden />
              </a>
            ) : null}
            {p.city || p.state ? <span>{[p.city, p.state].filter(Boolean).join(", ")}</span> : null}
            {p.partita_iva ? <span className="tnum">VAT {p.partita_iva}</span> : <span className="text-ink-3">No VAT number on file</span>}
          </>
        }
        actions={
          <Button
            variant="secondary"
            icon={<MessageSquareText className="size-4" />}
            onClick={() => assistant.ask(`Cosa sai di ${name}? Riassumi trattative aperte, ticket e ultimi contatti.`)}
          >
            Ask about this company
          </Button>
        }
      />

      <div className="grid flex-1 gap-4 p-6 lg:grid-cols-[minmax(0,2fr)_minmax(280px,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <Card className="overflow-hidden">
            <div className="grid gap-6 p-5 sm:grid-cols-[auto_1fr]">
              <ClassPlate value={p.classe_cliente} size="lg" />
              <div className="min-w-0">
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <span className="font-wide text-[34px] font-semibold tracking-tight text-ink pnum">{formatMoney(revenue, "EUR")}</span>
                  <span className="text-[13px] text-ink-2">revenue won in 2025</span>
                </div>
                <p className="mt-0.5 text-[13px] text-ink-2">
                  {p.classe_cliente ? (
                    <>
                      Class {p.classe_cliente}
                      {p.classe_cliente === "A" ? ", from €100,000 won in the year" : p.classe_cliente === "B" ? ", from €20,000 to €100,000 won in the year" : ", up to €20,000 won in the year"}
                    </>
                  ) : (
                    "No class: nothing won in 2025 after credit notes"
                  )}
                </p>
                <ClassScale revenue={revenue} className="mt-4 max-w-md" />
              </div>
            </div>
            <div className="grid grid-cols-2 divide-x divide-line border-t border-line bg-surface-2 sm:grid-cols-4">
              <Stat label="Open deals" value={String(openDeals.length)} sub={openDeals.length ? `${formatMoney(pipelineValue.total, "EUR", { compact: true })} in play` : undefined} />
              <Stat label="Won deals" value={String(wonDeals.length)} sub={deals.length ? `of ${deals.length} overall` : undefined} />
              <Stat label="Contacts" value={String(contacts.length)} />
              <Stat label="Open tickets" value={String(openTickets.length)} sub={tickets.length ? `${tickets.length} overall` : undefined} tone={openTickets.length ? "warn" : undefined} />
            </div>
          </Card>

          <Card>
            <Tabs defaultValue="deals">
              <TabsList className="px-2">
                <TabsTrigger value="deals" count={deals.length}>Deals</TabsTrigger>
                <TabsTrigger value="contacts" count={contacts.length}>Contacts</TabsTrigger>
                <TabsTrigger value="tickets" count={tickets.length}>Tickets</TabsTrigger>
                <TabsTrigger value="history" count={activities.data?.length}>History</TabsTrigger>
              </TabsList>

              <TabsContent value="deals">
                {deals.length === 0 ? (
                  <EmptyState compact title="No deals with this company" />
                ) : (
                  <Table>
                    <THead>
                      <TR>
                        <TH>Deal</TH>
                        <TH>Stage</TH>
                        <TH align="right">Amount</TH>
                        <TH>Close date</TH>
                        <TH>Owner</TH>
                      </TR>
                    </THead>
                    <TBody>
                      {deals
                        .slice()
                        .sort((a, b) => (Date.parse(b.properties.closedate ?? "") || 0) - (Date.parse(a.properties.closedate ?? "") || 0))
                        .map((d) => (
                          <TR key={d.id} interactive onClick={() => navigate(`/deals/${d.id}`)}>
                            <TD>
                              <RecordLink to={`/deals/${d.id}`}>{d.properties.dealname || "Untitled deal"}</RecordLink>
                              {d.properties.pipeline && d.properties.pipeline !== "default" ? <span className="ml-2 text-[12px] text-ink-3">Renewal</span> : null}
                            </TD>
                            <TD>
                              <StageBadge stage={stageOf(d)} stageId={d.properties.dealstage} size="sm" />
                            </TD>
                            <TD align="right" numeric>
                              <Money amount={d.properties.amount} currency={d.properties.deal_currency_code} />
                            </TD>
                            <TD muted>
                              <DateText value={d.properties.closedate} />
                            </TD>
                            <TD>
                              <OwnerChip email={d.properties.commerciale} size="xs" />
                            </TD>
                          </TR>
                        ))}
                    </TBody>
                  </Table>
                )}
              </TabsContent>

              <TabsContent value="contacts">
                {contacts.length === 0 ? (
                  <EmptyState compact title="No contacts linked" description="Contacts with an email at one of this company's domains are linked automatically." />
                ) : (
                  <Table>
                    <THead>
                      <TR>
                        <TH>Name</TH>
                        <TH>Email</TH>
                        <TH>Phone</TH>
                        <TH>Stage</TH>
                      </TR>
                    </THead>
                    <TBody>
                      {contacts.map((c) => (
                        <TR key={c.id} interactive onClick={() => navigate(`/contacts/${c.id}`)}>
                          <TD>
                            <div className="flex items-center gap-2">
                              <Avatar name={fullName(c.properties.firstname, c.properties.lastname)} size="sm" />
                              <div className="min-w-0">
                                <RecordLink to={`/contacts/${c.id}`}>{fullName(c.properties.firstname, c.properties.lastname)}</RecordLink>
                                {c.properties.jobtitle ? <div className="text-[12px] text-ink-3">{c.properties.jobtitle}</div> : null}
                              </div>
                            </div>
                          </TD>
                          <TD muted>{c.properties.email || <span className="text-ink-3">–</span>}</TD>
                          <TD muted numeric>{c.properties.phone || <span className="text-ink-3">–</span>}</TD>
                          <TD>
                            <LifecycleBadge value={c.properties.lifecyclestage} size="sm" />
                          </TD>
                        </TR>
                      ))}
                    </TBody>
                  </Table>
                )}
              </TabsContent>

              <TabsContent value="tickets">
                {tickets.length === 0 ? (
                  <EmptyState compact title="No support tickets" />
                ) : (
                  <Table>
                    <THead>
                      <TR>
                        <TH>Subject</TH>
                        <TH>Status</TH>
                        <TH>Priority</TH>
                        <TH>Owner</TH>
                        <TH align="right">Opened</TH>
                      </TR>
                    </THead>
                    <TBody>
                      {tickets
                        .slice()
                        .sort((a, b) => (Date.parse(b.properties.createdate ?? "") || 0) - (Date.parse(a.properties.createdate ?? "") || 0))
                        .map((t) => (
                          <TR key={t.id} interactive onClick={() => navigate(`/tickets/${t.id}`)}>
                            <TD>
                              <RecordLink to={`/tickets/${t.id}`}>{t.properties.subject || "Untitled ticket"}</RecordLink>
                            </TD>
                            <TD>
                              <TicketStageBadge stage={ticketStageOf(t)} stageId={t.properties.hs_pipeline_stage} size="sm" />
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
                          </TR>
                        ))}
                    </TBody>
                  </Table>
                )}
              </TabsContent>

              <TabsContent value="history">
                <NoteComposer target={{ type: "companies", id: company.id }} />
                <div className="flex items-center gap-1 border-b border-line px-3 py-1.5 text-[12px]">
                  {(["all", "notes", "calls", "emails", "meetings", "tasks"] as const).map((k) => (
                    <button
                      key={k}
                      type="button"
                      onClick={() => setHistoryFilter(k)}
                      className={historyFilter === k ? "rounded-sm bg-surface-3 px-2 py-0.5 font-medium text-ink" : "rounded-sm px-2 py-0.5 text-ink-2 hover:text-ink"}
                    >
                      {k === "all" ? "All" : k[0]!.toUpperCase() + k.slice(1)}
                    </button>
                  ))}
                </div>
                <ActivityFeed activities={activities.data} isLoading={activities.isPending && activities.fetchStatus !== "idle"} error={activities.error} onRetry={() => activities.refetch()} filter={historyFilter} />
              </TabsContent>
            </Tabs>
          </Card>
        </div>

        <div className="flex min-w-0 flex-col gap-4">
          <Card>
            <CardHeader title="Details" />
            <CardBody>
              <PropertyList
                items={[
                  { label: "Name", value: p.name },
                  { label: "Website", value: domains.length ? domains.map((d) => <div key={d}>{d}</div>) : null },
                  { label: "City", value: p.city },
                  { label: "Province", value: p.state },
                  { label: "VAT number", value: p.partita_iva ? <span className="tnum">{p.partita_iva}</span> : null },
                  { label: "Phone", value: p.phone },
                  { label: "Notes", value: p.description },
                  { label: "Legacy id", value: p.id_legacy ? <span className="tnum">{p.id_legacy}</span> : null },
                  { label: "Created", value: <DateText value={p.createdate ?? company.createdAt} /> },
                  { label: "Updated", value: <DateText value={p.hs_lastmodifieddate ?? company.updatedAt} withTime /> },
                ]}
              />
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Who works this account" meta={owners.length ? `${owners.length}` : undefined} />
            <CardBody className="p-2">
              {owners.length === 0 ? (
                <p className="px-2 py-1 text-[13px] text-ink-3">No deals or tickets assigned yet.</p>
              ) : (
                <ul className="divide-y divide-line">
                  {owners.map((email) => {
                    const dealsOwned = deals.filter((d) => d.properties.commerciale === email).length;
                    const ticketsOwned = tickets.filter((t) => t.properties.assegnatario === email).length;
                    return (
                      <li key={email} className="flex items-center gap-2.5 px-2 py-2">
                        <Avatar name={userName(email)} size="md" />
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-[13px] font-medium text-ink">{userName(email)}</div>
                          <div className="truncate text-[12px] text-ink-3">
                            {[dealsOwned ? `${dealsOwned} ${dealsOwned === 1 ? "deal" : "deals"}` : null, ticketsOwned ? `${ticketsOwned} ${ticketsOwned === 1 ? "ticket" : "tickets"}` : null].filter(Boolean).join(" · ")}
                          </div>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </CardBody>
          </Card>

          <p className="px-1 text-[12px] text-ink-3">
            Revenue and class are computed by the migration from deals won in 2025, net of credit notes, at fixed USD and GBP rates.{" "}
            <Link to="/dormant" className="text-gentian hover:underline">
              See dormant customers
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: "warn" }) {
  return (
    <div className="px-4 py-3">
      <div className="text-[12px] text-ink-2">{label}</div>
      <div className={tone === "warn" && value !== "0" ? "mt-0.5 font-wide text-[20px] font-semibold text-warn pnum" : "mt-0.5 font-wide text-[20px] font-semibold text-ink pnum"}>{value}</div>
      {sub ? <div className="text-[12px] text-ink-3">{sub}</div> : null}
    </div>
  );
}
