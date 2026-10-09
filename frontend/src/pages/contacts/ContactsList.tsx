import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Users } from "lucide-react";
import { useContacts } from "@/api/hooks";
import type { ContactListParams } from "@/api/endpoints";
import { PageHeader } from "@/components/layout/PageHeader";
import { NativeSelect, SearchInput } from "@/components/ui/Input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { SkeletonRows } from "@/components/ui/Skeleton";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { LoadMoreFooter } from "@/components/ui/LoadMore";
import { Avatar } from "@/components/ui/Avatar";
import { LifecycleBadge } from "@/components/crm/Badges";
import { RecordLink, RelativeTime } from "@/components/crm/Values";
import { useListParams } from "@/lib/useListParams";
import { formatNumber, fullName } from "@/lib/format";
import { useDebounced } from "@/lib/useDebounced";
import { LIFECYCLE_LABELS } from "@/lib/stages";

const KEYS = ["q", "stage"] as const;
const DEFAULTS = {} as const;

export function ContactsList() {
  const navigate = useNavigate();
  const [params, setParams] = useListParams(KEYS, DEFAULTS);
  const q = useDebounced(params.q, 250);
  const queryParams = useMemo<ContactListParams>(() => ({ query: q, lifecyclestage: params.stage || undefined }), [q, params.stage]);
  const query = useContacts(queryParams);
  const rows = query.data?.pages.flatMap((p) => p.results) ?? [];
  const total = query.data?.pages[0]?.total;

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader title="Contacts" meta={total !== undefined ? <span className="tnum">{formatNumber(total)} contacts</span> : undefined}>
        <div className="flex flex-wrap items-center gap-2 pb-3">
          <SearchInput value={params.q} onChange={(v) => setParams({ q: v })} placeholder="Search by name or email" className="w-72" />
          <NativeSelect
            aria-label="Lifecycle stage"
            value={params.stage}
            onChange={(e) => setParams({ stage: e.target.value })}
            placeholder="Any stage"
            options={["lead", "opportunity", "customer", "other"].map((v) => ({ value: v, label: LIFECYCLE_LABELS[v]! }))}
            className="w-44"
          />
        </div>
      </PageHeader>
      <div className="flex-1 bg-surface">
        {query.isPending ? (
          <SkeletonRows rows={10} cols={5} />
        ) : query.isError ? (
          <ErrorState error={query.error} onRetry={() => query.refetch()} title="Could not load contacts" />
        ) : rows.length === 0 ? (
          <EmptyState icon={<Users />} title={q || params.stage ? "No contacts match" : "No contacts yet"} description={q || params.stage ? "Try a different search or clear the filter." : "Contacts arrive with the migration from Sinergia."} />
        ) : (
          <>
            <Table>
              <THead>
                <TR>
                  <TH>Name</TH>
                  <TH>Email</TH>
                  <TH>Phone</TH>
                  <TH>Company</TH>
                  <TH>Stage</TH>
                  <TH align="right">Updated</TH>
                </TR>
              </THead>
              <TBody>
                {rows.map((c) => {
                  const name = fullName(c.properties.firstname, c.properties.lastname);
                  return (
                    <TR key={c.id} interactive onClick={() => navigate(`/contacts/${c.id}`)}>
                      <TD>
                        <div className="flex items-center gap-2.5">
                          <Avatar name={name} size="md" />
                          <div className="min-w-0">
                            <div className="truncate font-medium text-ink">{name}</div>
                            {c.properties.jobtitle ? <div className="truncate text-[12px] text-ink-3">{c.properties.jobtitle}</div> : null}
                          </div>
                        </div>
                      </TD>
                      <TD muted>{c.properties.email || <span className="text-ink-3">No email</span>}</TD>
                      <TD muted numeric>{c.properties.phone || <span className="text-ink-3">–</span>}</TD>
                      <TD>
                        {c.properties.associatedcompanyid ? (
                          <RecordLink to={`/companies/${c.properties.associatedcompanyid}`} className="font-normal text-ink-2">
                            {c.properties.company || "View company"}
                          </RecordLink>
                        ) : c.properties.company ? (
                          <span className="text-ink-2">{c.properties.company}</span>
                        ) : (
                          <span className="text-ink-3">No company</span>
                        )}
                      </TD>
                      <TD>
                        <LifecycleBadge value={c.properties.lifecyclestage} size="sm" />
                      </TD>
                      <TD align="right" muted>
                        <RelativeTime value={c.properties.lastmodifieddate ?? c.updatedAt} />
                      </TD>
                    </TR>
                  );
                })}
              </TBody>
            </Table>
            <LoadMoreFooter shown={rows.length} total={total} hasMore={Boolean(query.hasNextPage)} loading={query.isFetchingNextPage} onMore={() => query.fetchNextPage()} noun="contacts" />
          </>
        )}
      </div>
    </div>
  );
}
