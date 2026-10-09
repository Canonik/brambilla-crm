import { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Mail, MessageSquareText, Phone } from "lucide-react";
import { useActivities, useContactPage, usePipelines } from "@/api/hooks";
import { useAssistant } from "@/assistant/AssistantContext";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Avatar } from "@/components/ui/Avatar";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { Skeleton, SkeletonBlock } from "@/components/ui/Skeleton";
import { ClassPlate } from "@/components/crm/ClassPlate";
import { LifecycleBadge, PriorityBadge, StageBadge, TicketStageBadge } from "@/components/crm/Badges";
import { DateText, Money, OwnerChip, PropertyList, RecordLink } from "@/components/crm/Values";
import { ActivityFeed, NoteComposer } from "@/components/crm/ActivityFeed";
import { fullName } from "@/lib/format";

export function ContactDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const page = useContactPage(id);
  const dealPipelines = usePipelines("deals");
  const ticketPipelines = usePipelines("tickets");
  const assistant = useAssistant();
  const targets = useMemo(() => [{ type: "contacts" as const, ids: id ? [id] : [] }], [id]);
  const activities = useActivities(`contact:${id}`, targets, page.isSuccess);

  if (page.isPending) {
    return (
      <div className="flex flex-1 flex-col">
        <PageHeader title={<Skeleton className="h-6 w-56" />} crumbs={[{ label: "Contacts", to: "/contacts" }, { label: "Loading" }]} />
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
        <PageHeader title="Contact" crumbs={[{ label: "Contacts", to: "/contacts" }, { label: "Not found" }]} />
        <ErrorState error={page.error} onRetry={() => page.refetch()} title="Could not load this contact" />
      </div>
    );
  }

  const { contact, companies, deals, tickets } = page.data;
  const p = contact.properties;
  const name = fullName(p.firstname, p.lastname);
  const company = companies[0];

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        crumbs={[{ label: "Contacts", to: "/contacts" }, { label: name }]}
        leading={<Avatar name={name} size="lg" />}
        title={name}
        meta={
          <>
            {p.jobtitle ? <span>{p.jobtitle}</span> : null}
            {company ? <RecordLink to={`/companies/${company.id}`} className="font-normal text-ink-2">{company.properties.name}</RecordLink> : <span className="text-ink-3">No company</span>}
            <LifecycleBadge value={p.lifecyclestage} size="sm" />
          </>
        }
        actions={
          <>
            {p.email ? (
              <a href={`mailto:${p.email}`} className="inline-flex h-8 items-center gap-2 rounded-md border border-line-strong bg-surface px-3 text-[13px] font-medium text-ink hover:bg-surface-2">
                <Mail className="size-4" /> Email
              </a>
            ) : null}
            {p.phone ? (
              <a href={`tel:${p.phone}`} className="inline-flex h-8 items-center gap-2 rounded-md border border-line-strong bg-surface px-3 text-[13px] font-medium text-ink hover:bg-surface-2">
                <Phone className="size-4" /> Call
              </a>
            ) : null}
            <Button variant="secondary" icon={<MessageSquareText className="size-4" />} onClick={() => assistant.ask(`Cosa sappiamo di ${name}${company ? ` di ${company.properties.name}` : ""}? Ultime attività e trattative.`)}>
              Ask about this contact
            </Button>
          </>
        }
      />
      <div className="grid flex-1 gap-4 p-6 lg:grid-cols-[minmax(0,2fr)_minmax(280px,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <Card>
            <CardHeader title="Deals" meta={deals.length || undefined} />
            {deals.length === 0 ? (
              <EmptyState compact title="No deals with this contact" />
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
                  {deals.map((d) => {
                    const stage = dealPipelines.data?.find((pl) => pl.id === (d.properties.pipeline || "default"))?.stages.find((s) => s.id === d.properties.dealstage);
                    return (
                      <TR key={d.id} interactive onClick={() => navigate(`/deals/${d.id}`)}>
                        <TD>
                          <RecordLink to={`/deals/${d.id}`}>{d.properties.dealname || "Untitled deal"}</RecordLink>
                        </TD>
                        <TD>
                          <StageBadge stage={stage} stageId={d.properties.dealstage} size="sm" />
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
                    );
                  })}
                </TBody>
              </Table>
            )}
          </Card>

          <Card>
            <CardHeader title="Tickets" meta={tickets.length || undefined} />
            {tickets.length === 0 ? (
              <EmptyState compact title="No tickets from this contact" />
            ) : (
              <Table>
                <THead>
                  <TR>
                    <TH>Subject</TH>
                    <TH>Status</TH>
                    <TH>Priority</TH>
                    <TH>Opened</TH>
                  </TR>
                </THead>
                <TBody>
                  {tickets.map((t) => {
                    const stage = ticketPipelines.data?.flatMap((pl) => pl.stages).find((s) => s.id === t.properties.hs_pipeline_stage);
                    return (
                      <TR key={t.id} interactive onClick={() => navigate(`/tickets/${t.id}`)}>
                        <TD>
                          <RecordLink to={`/tickets/${t.id}`}>{t.properties.subject || "Untitled ticket"}</RecordLink>
                        </TD>
                        <TD>
                          <TicketStageBadge stage={stage} stageId={t.properties.hs_pipeline_stage} size="sm" />
                        </TD>
                        <TD>
                          <PriorityBadge value={t.properties.hs_ticket_priority} size="sm" />
                        </TD>
                        <TD muted>
                          <DateText value={t.properties.createdate} />
                        </TD>
                      </TR>
                    );
                  })}
                </TBody>
              </Table>
            )}
          </Card>

          <Card>
            <CardHeader title="History" meta={activities.data?.length || undefined} />
            <NoteComposer target={{ type: "contacts", id: contact.id }} />
            <ActivityFeed activities={activities.data} isLoading={activities.isPending && activities.fetchStatus !== "idle"} error={activities.error} onRetry={() => activities.refetch()} />
          </Card>
        </div>

        <div className="flex min-w-0 flex-col gap-4">
          <Card>
            <CardHeader title="Details" />
            <CardBody>
              <PropertyList
                items={[
                  { label: "Email", value: p.email ? <a href={`mailto:${p.email}`} className="break-all hover:text-gentian hover:underline">{p.email}</a> : null },
                  { label: "Phone", value: p.phone ? <span className="tnum">{p.phone}</span> : null },
                  { label: "Job title", value: p.jobtitle },
                  { label: "Stage", value: <LifecycleBadge value={p.lifecyclestage} size="sm" /> },
                  { label: "Legacy id", value: p.id_legacy ? <span className="tnum">{p.id_legacy}</span> : null },
                  { label: "Created", value: <DateText value={p.createdate ?? contact.createdAt} /> },
                  { label: "Updated", value: <DateText value={p.lastmodifieddate ?? contact.updatedAt} withTime /> },
                ]}
              />
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="Company" />
            <CardBody className="p-2">
              {companies.length === 0 ? (
                <p className="px-2 py-1 text-[13px] text-ink-3">Not linked to a company. A contact is linked automatically when its email domain matches a company's website.</p>
              ) : (
                <ul className="divide-y divide-line">
                  {companies.map((c) => (
                    <li key={c.id}>
                      <RecordLink to={`/companies/${c.id}`} className="flex items-center gap-2.5 rounded-md px-2 py-2 font-normal hover:bg-surface-2 hover:no-underline">
                        <Avatar name={c.properties.name} size="md" square />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13px] font-medium text-ink">{c.properties.name}</span>
                          <span className="block truncate text-[12px] text-ink-3">{[c.properties.city, c.properties.state].filter(Boolean).join(", ") || c.properties.domain}</span>
                        </span>
                        <ClassPlate value={c.properties.classe_cliente} size="sm" />
                      </RecordLink>
                    </li>
                  ))}
                </ul>
              )}
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
