import { useMemo } from "react";
import { useParams } from "react-router-dom";
import { MessageSquareText } from "lucide-react";
import { useActivities, usePipelines, useTicketPage, useUpdateTicket } from "@/api/hooks";
import { useAssistant } from "@/assistant/AssistantContext";
import { useCurrentUser } from "@/app/currentUser";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Avatar } from "@/components/ui/Avatar";
import { Label, NativeSelect } from "@/components/ui/Input";
import { ErrorState } from "@/components/ui/States";
import { Skeleton, SkeletonBlock } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toaster";
import { ClassPlate } from "@/components/crm/ClassPlate";
import { PriorityBadge, StageBadge, TicketStageBadge } from "@/components/crm/Badges";
import { DateText, Money, OwnerChip, PropertyList, RecordLink } from "@/components/crm/Values";
import { ActivityFeed, NoteComposer } from "@/components/crm/ActivityFeed";
import { fullName } from "@/lib/format";
import { displayStageLabel } from "@/lib/stages";
import { userName } from "@/api/users";

export function TicketDetail() {
  const { id } = useParams<{ id: string }>();
  const page = useTicketPage(id);
  const pipelines = usePipelines("tickets");
  const dealPipelines = usePipelines("deals");
  const assistant = useAssistant();
  const { users } = useCurrentUser();
  const toast = useToast();
  const update = useUpdateTicket(id ?? "");
  const targets = useMemo(() => [{ type: "tickets" as const, ids: id ? [id] : [] }], [id]);
  const activities = useActivities(`ticket:${id}`, targets, page.isSuccess);

  if (page.isPending) {
    return (
      <div className="flex flex-1 flex-col">
        <PageHeader title={<Skeleton className="h-6 w-72" />} crumbs={[{ label: "Tickets", to: "/tickets" }, { label: "Loading" }]} />
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
        <PageHeader title="Ticket" crumbs={[{ label: "Tickets", to: "/tickets" }, { label: "Not found" }]} />
        <ErrorState error={page.error} onRetry={() => page.refetch()} title="Could not load this ticket" />
      </div>
    );
  }

  const { ticket, companies, contacts, deals } = page.data;
  const p = ticket.properties;
  const subject = p.subject || "Untitled ticket";
  const pipeline = pipelines.data?.find((pl) => pl.id === p.hs_pipeline) ?? pipelines.data?.[0];
  const stages = pipeline?.stages ?? [];
  const stage = stages.find((s) => s.id === p.hs_pipeline_stage);
  const company = companies[0];
  const contact = contacts[0];
  const deal = deals[0];

  const patch = async (props: Record<string, string>, label: string) => {
    try {
      await update.mutateAsync(props);
      toast.success(label);
    } catch (err) {
      toast.error("Could not update the ticket", err instanceof Error ? err.message : undefined);
    }
  };

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        crumbs={[{ label: "Tickets", to: "/tickets" }, { label: subject }]}
        title={subject}
        eyebrow={p.id_legacy ? <span className="tnum">Ticket {p.id_legacy}</span> : <span className="tnum">Ticket {ticket.id}</span>}
        meta={
          <>
            <TicketStageBadge stage={stage} stageId={p.hs_pipeline_stage} />
            <PriorityBadge value={p.hs_ticket_priority} />
            <span>
              Opened <DateText value={p.createdate ?? ticket.createdAt} withTime />
            </span>
            {p.closed_date ? (
              <span>
                Closed <DateText value={p.closed_date} withTime />
              </span>
            ) : null}
          </>
        }
        actions={
          <Button variant="secondary" icon={<MessageSquareText className="size-4" />} onClick={() => assistant.ask(`Riassumi il ticket "${subject}"${company ? ` di ${company.properties.name}` : ""} e proponi la prossima azione.`)}>
            Ask about this ticket
          </Button>
        }
      />

      <div className="grid flex-1 gap-4 p-6 lg:grid-cols-[minmax(0,2fr)_minmax(300px,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <Card>
            <CardHeader title="Description" />
            <CardBody>
              {p.content ? <p className="whitespace-pre-line text-[14px] leading-relaxed text-ink">{p.content}</p> : <p className="text-[13px] text-ink-3">No description was written on this ticket.</p>}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Notes and history" meta={activities.data?.length || undefined} />
            <NoteComposer target={{ type: "tickets", id: ticket.id }} />
            <ActivityFeed activities={activities.data} isLoading={activities.isPending && activities.fetchStatus !== "idle"} error={activities.error} onRetry={() => activities.refetch()} />
          </Card>
        </div>

        <div className="flex min-w-0 flex-col gap-4">
          <Card>
            <CardHeader title="Work the ticket" />
            <CardBody className="grid gap-3">
              <div>
                <Label htmlFor="ticket-status">Status</Label>
                <NativeSelect
                  id="ticket-status"
                  className="mt-1"
                  value={p.hs_pipeline_stage ?? ""}
                  disabled={update.isPending || stages.length === 0}
                  onChange={(e) => void patch({ hs_pipeline_stage: e.target.value }, `Status set to ${displayStageLabel(stages.find((s) => s.id === e.target.value))}`)}
                  options={stages.map((s) => ({ value: s.id, label: displayStageLabel(s) }))}
                />
              </div>
              <div>
                <Label htmlFor="ticket-priority">Priority</Label>
                <NativeSelect
                  id="ticket-priority"
                  className="mt-1"
                  value={p.hs_ticket_priority ?? ""}
                  disabled={update.isPending}
                  placeholder="No priority"
                  onChange={(e) => void patch({ hs_ticket_priority: e.target.value }, e.target.value ? "Priority updated" : "Priority cleared")}
                  options={[
                    { value: "URGENT", label: "Urgent" },
                    { value: "HIGH", label: "High" },
                    { value: "MEDIUM", label: "Medium" },
                    { value: "LOW", label: "Low" },
                  ]}
                />
              </div>
              <div>
                <Label htmlFor="ticket-owner">Assigned to</Label>
                <NativeSelect
                  id="ticket-owner"
                  className="mt-1"
                  value={p.assegnatario ?? ""}
                  disabled={update.isPending}
                  placeholder="Unassigned"
                  onChange={(e) => void patch({ assegnatario: e.target.value }, "Assignee updated")}
                  options={[
                    ...users.map((u) => ({ value: u.email, label: u.name })),
                    ...(p.assegnatario && !users.some((u) => u.email === p.assegnatario!.toLowerCase())
                      ? [{ value: p.assegnatario, label: `${userName(p.assegnatario)} (not active)` }]
                      : []),
                  ]}
                />
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Linked records" />
            <CardBody className="p-2">
              <ul className="divide-y divide-line">
                <li className="px-2 py-2">
                  <div className="mb-1 text-[11.5px] text-ink-3">Company</div>
                  {company ? (
                    <RecordLink to={`/companies/${company.id}`} className="flex items-center gap-2 font-normal">
                      <Avatar name={company.properties.name} size="sm" square />
                      <span className="min-w-0 flex-1 truncate text-[13px] font-medium">{company.properties.name}</span>
                      <ClassPlate value={company.properties.classe_cliente} size="sm" />
                    </RecordLink>
                  ) : (
                    <span className="text-[13px] text-ink-3">None</span>
                  )}
                </li>
                <li className="px-2 py-2">
                  <div className="mb-1 text-[11.5px] text-ink-3">Contact</div>
                  {contact ? (
                    <RecordLink to={`/contacts/${contact.id}`} className="flex items-center gap-2 font-normal">
                      <Avatar name={fullName(contact.properties.firstname, contact.properties.lastname)} size="sm" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13px] font-medium">{fullName(contact.properties.firstname, contact.properties.lastname)}</span>
                        <span className="block truncate text-[12px] text-ink-3">{contact.properties.email}</span>
                      </span>
                    </RecordLink>
                  ) : (
                    <span className="text-[13px] text-ink-3">None</span>
                  )}
                </li>
                <li className="px-2 py-2">
                  <div className="mb-1 text-[11.5px] text-ink-3">Deal</div>
                  {deal ? (
                    <RecordLink to={`/deals/${deal.id}`} className="block font-normal">
                      <span className="block truncate text-[13px] font-medium">{deal.properties.dealname}</span>
                      <span className="mt-1 flex items-center gap-2">
                        <StageBadge stage={dealPipelines.data?.find((pl) => pl.id === (deal.properties.pipeline || "default"))?.stages.find((s) => s.id === deal.properties.dealstage)} stageId={deal.properties.dealstage} size="sm" />
                        <Money amount={deal.properties.amount} currency={deal.properties.deal_currency_code} className="text-[12px] text-ink-2" />
                      </span>
                    </RecordLink>
                  ) : (
                    <span className="text-[13px] text-ink-3">None</span>
                  )}
                </li>
              </ul>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Details" />
            <CardBody>
              <PropertyList
                items={[
                  { label: "Owner", value: <OwnerChip email={p.assegnatario} size="xs" /> },
                  { label: "Pipeline", value: pipeline ? "Support" : p.hs_pipeline },
                  { label: "Opened", value: <DateText value={p.createdate ?? ticket.createdAt} withTime /> },
                  { label: "Closed", value: <DateText value={p.closed_date} withTime /> },
                  { label: "Legacy id", value: p.id_legacy ? <span className="tnum">{p.id_legacy}</span> : null },
                  { label: "Updated", value: <DateText value={p.hs_lastmodifieddate ?? ticket.updatedAt} withTime /> },
                ]}
              />
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
