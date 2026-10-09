import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Building2 } from "lucide-react";
import { useCompanies } from "@/api/hooks";
import type { CompanyListParams } from "@/api/endpoints";
import { PageHeader } from "@/components/layout/PageHeader";
import { NativeSelect, SearchInput } from "@/components/ui/Input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { SkeletonRows } from "@/components/ui/Skeleton";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { LoadMoreFooter } from "@/components/ui/LoadMore";
import { Avatar } from "@/components/ui/Avatar";
import { ClassPlate } from "@/components/crm/ClassPlate";
import { Money, RelativeTime } from "@/components/crm/Values";
import { useListParams } from "@/lib/useListParams";
import { formatNumber } from "@/lib/format";
import { useDebounced } from "@/lib/useDebounced";

const KEYS = ["q", "class", "sort"] as const;
const DEFAULTS = { sort: "name" } as const;

const SORTS: Array<{ value: string; label: string; by: CompanyListParams["sortBy"]; dir: CompanyListParams["sortDir"] }> = [
  { value: "name", label: "Name A to Z", by: "name", dir: "ASCENDING" },
  { value: "revenue", label: "Revenue 2025, highest first", by: "fatturato_2025", dir: "DESCENDING" },
  { value: "updated", label: "Recently updated", by: "hs_lastmodifieddate", dir: "DESCENDING" },
  { value: "city", label: "City", by: "city", dir: "ASCENDING" },
];

export function CompaniesList() {
  const navigate = useNavigate();
  const [params, setParams] = useListParams(KEYS, DEFAULTS);
  const q = useDebounced(params.q, 250);
  const sort = SORTS.find((s) => s.value === params.sort) ?? SORTS[0]!;

  const queryParams = useMemo<CompanyListParams>(
    () => ({ query: q, classe: params.class || undefined, sortBy: sort.by, sortDir: sort.dir }),
    [q, params.class, sort],
  );
  const query = useCompanies(queryParams);
  const rows = query.data?.pages.flatMap((p) => p.results) ?? [];
  const total = query.data?.pages[0]?.total;

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Companies"
        meta={total !== undefined ? <span className="tnum">{formatNumber(total)} companies</span> : undefined}
      >
        <div className="flex flex-wrap items-center gap-2 pb-3">
          <SearchInput value={params.q} onChange={(v) => setParams({ q: v })} placeholder="Search by name, domain or city" className="w-72" />
          <NativeSelect
            aria-label="Customer class"
            value={params.class}
            onChange={(e) => setParams({ class: e.target.value })}
            placeholder="Any class"
            options={[
              { value: "A", label: "Class A" },
              { value: "B", label: "Class B" },
              { value: "C", label: "Class C" },
            ]}
            className="w-36"
          />
          <NativeSelect
            aria-label="Sort"
            value={params.sort}
            onChange={(e) => setParams({ sort: e.target.value })}
            options={SORTS.map((s) => ({ value: s.value, label: s.label }))}
            className="w-56"
          />
        </div>
      </PageHeader>

      <div className="flex-1 bg-surface">
        {query.isPending ? (
          <SkeletonRows rows={10} cols={5} />
        ) : query.isError ? (
          <ErrorState error={query.error} onRetry={() => query.refetch()} title="Could not load companies" />
        ) : rows.length === 0 ? (
          <EmptyState
            icon={<Building2 />}
            title={q || params.class ? "No companies match" : "No companies yet"}
            description={q || params.class ? "Try a different search or clear the class filter." : "Companies arrive with the migration from Sinergia."}
          />
        ) : (
          <>
            <Table>
              <THead>
                <TR>
                  <TH>Company</TH>
                  <TH>Location</TH>
                  <TH align="center">Class</TH>
                  <TH align="right">Revenue 2025</TH>
                  <TH>VAT number</TH>
                  <TH align="right">Updated</TH>
                </TR>
              </THead>
              <TBody>
                {rows.map((c) => (
                  <TR
                    key={c.id}
                    interactive
                    tabIndex={0}
                    onClick={() => navigate(`/companies/${c.id}`)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") navigate(`/companies/${c.id}`);
                    }}
                  >
                    <TD>
                      <div className="flex items-center gap-2.5">
                        <Avatar name={c.properties.name} size="md" square />
                        <div className="min-w-0">
                          <div className="truncate font-medium text-ink">{c.properties.name || "Unnamed company"}</div>
                          <div className="truncate text-[12px] text-ink-3">{c.properties.domain || "No website"}</div>
                        </div>
                      </div>
                    </TD>
                    <TD muted>
                      {c.properties.city || c.properties.state ? (
                        <>
                          {c.properties.city}
                          {c.properties.state ? <span className="text-ink-3"> {c.properties.city ? "·" : ""} {c.properties.state}</span> : null}
                        </>
                      ) : (
                        <span className="text-ink-3">–</span>
                      )}
                    </TD>
                    <TD align="center">
                      <ClassPlate value={c.properties.classe_cliente} size="sm" emptyAs="dash" />
                    </TD>
                    <TD align="right" numeric>
                      <Money amount={c.properties.fatturato_2025} currency="EUR" muted={!Number(c.properties.fatturato_2025)} />
                    </TD>
                    <TD muted numeric>
                      {c.properties.partita_iva || <span className="text-ink-3">–</span>}
                    </TD>
                    <TD align="right" muted>
                      <RelativeTime value={c.properties.hs_lastmodifieddate ?? c.updatedAt} />
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
            <LoadMoreFooter
              shown={rows.length}
              total={total}
              hasMore={Boolean(query.hasNextPage)}
              loading={query.isFetchingNextPage}
              onMore={() => query.fetchNextPage()}
              noun="companies"
            />
          </>
        )}
      </div>
    </div>
  );
}
