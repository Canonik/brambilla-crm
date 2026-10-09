import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Moon } from "lucide-react";
import { useDormantCompanies } from "@/api/hooks";
import type { Company } from "@/api/types";
import { useAssistant } from "@/assistant/AssistantContext";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { SearchInput } from "@/components/ui/Input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { SkeletonRows } from "@/components/ui/Skeleton";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { LoadMoreFooter } from "@/components/ui/LoadMore";
import { Avatar } from "@/components/ui/Avatar";
import { ClassPlate } from "@/components/crm/ClassPlate";
import { Money } from "@/components/crm/Values";
import { formatNumber, toNumber } from "@/lib/format";
import { DORMANT_LIST_NAME } from "@/api/endpoints";

type SortKey = "name" | "revenue" | "class" | "location";

const CLASS_RANK: Record<string, number> = { A: 3, B: 2, C: 1 };

function sortRows(rows: Company[], key: SortKey, dir: 1 | -1) {
  const cmp = (a: Company, b: Company) => {
    switch (key) {
      case "revenue":
        return (toNumber(a.properties.fatturato_2025) ?? 0) - (toNumber(b.properties.fatturato_2025) ?? 0);
      case "class":
        return (CLASS_RANK[a.properties.classe_cliente ?? ""] ?? 0) - (CLASS_RANK[b.properties.classe_cliente ?? ""] ?? 0);
      case "location":
        return `${a.properties.state ?? ""} ${a.properties.city ?? ""}`.localeCompare(`${b.properties.state ?? ""} ${b.properties.city ?? ""}`, "en");
      default:
        return (a.properties.name ?? "").localeCompare(b.properties.name ?? "", "en", { sensitivity: "base" });
    }
  };
  return rows.slice().sort((a, b) => dir * cmp(a, b));
}

export function DormantCustomers() {
  const navigate = useNavigate();
  const query = useDormantCompanies();
  const assistant = useAssistant();
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "revenue", dir: -1 });

  const list = query.data?.pages[0]?.list;
  const loaded = useMemo(() => query.data?.pages.flatMap((p) => p.companies) ?? [], [query.data]);
  const total = query.data?.pages[0]?.total ?? (query.hasNextPage ? undefined : loaded.length);
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const rows = needle
      ? loaded.filter((c) => [c.properties.name, c.properties.domain, c.properties.city, c.properties.state, c.properties.partita_iva].some((v) => (v ?? "").toLowerCase().includes(needle)))
      : loaded;
    return sortRows(rows, sort.key, sort.dir);
  }, [loaded, q, sort]);

  const toggleSort = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === 1 ? -1 : 1 } : { key, dir: key === "name" || key === "location" ? 1 : -1 }));
  const sortState = (key: SortKey) => (sort.key === key ? (sort.dir === 1 ? "asc" : "desc") : null);

  const withRevenue = loaded.filter((c) => (toNumber(c.properties.fatturato_2025) ?? 0) > 0).length;

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Dormant customers"
        meta={
          <>
            <span>Customers with at least one won deal and no activity logged in 2025</span>
            {total !== undefined ? <span className="tnum text-ink">{formatNumber(total)} companies</span> : null}
          </>
        }
        actions={
          <Button variant="secondary" icon={<Moon className="size-4" />} onClick={() => assistant.ask("Quali clienti dormienti seguo io? Dammi i primi dieci con l'ultima trattativa vinta.")}>
            Ask who to call first
          </Button>
        }
      >
        <div className="flex flex-wrap items-center gap-2 pb-3">
          <SearchInput value={q} onChange={setQ} placeholder="Filter loaded companies" className="w-72" />
          {loaded.length ? (
            <span className="text-[12.5px] text-ink-3 tnum">
              {withRevenue} of {loaded.length} loaded still bought something in 2025
            </span>
          ) : null}
        </div>
      </PageHeader>

      <div className="flex-1 bg-surface">
        {query.isPending ? (
          <SkeletonRows rows={10} cols={5} />
        ) : query.isError ? (
          <ErrorState error={query.error} onRetry={() => query.refetch()} title="Could not load the dormant customers" />
        ) : !list ? (
          <EmptyState
            icon={<Moon />}
            title={`The "${DORMANT_LIST_NAME}" list is not there yet`}
            description="The migration builds it from the Sinergia export: companies with a won deal in any year and no note, call, email or meeting in 2025. Run the migration, then come back."
            action={
              <Button variant="secondary" onClick={() => query.refetch()}>
                Check again
              </Button>
            }
          />
        ) : filtered.length === 0 ? (
          <EmptyState icon={<Moon />} title={q ? "No loaded companies match" : "Nobody is dormant"} description={q ? "Load more or change the filter." : "Every customer with a won deal had some activity in 2025."} />
        ) : (
          <>
            <Table>
              <THead>
                <TR>
                  <TH sort={sortState("name")} onSort={() => toggleSort("name")}>Company</TH>
                  <TH sort={sortState("location")} onSort={() => toggleSort("location")}>Location</TH>
                  <TH align="center" sort={sortState("class")} onSort={() => toggleSort("class")}>Class</TH>
                  <TH align="right" sort={sortState("revenue")} onSort={() => toggleSort("revenue")}>Revenue 2025</TH>
                  <TH>VAT number</TH>
                  <TH>Website</TH>
                </TR>
              </THead>
              <TBody>
                {filtered.map((c) => (
                  <TR key={c.id} interactive onClick={() => navigate(`/companies/${c.id}`)}>
                    <TD>
                      <div className="flex items-center gap-2.5">
                        <Avatar name={c.properties.name} size="md" square />
                        <span className="truncate font-medium text-ink">{c.properties.name || "Unnamed company"}</span>
                      </div>
                    </TD>
                    <TD muted>{[c.properties.city, c.properties.state].filter(Boolean).join(", ") || <span className="text-ink-3">–</span>}</TD>
                    <TD align="center">
                      <ClassPlate value={c.properties.classe_cliente} size="sm" emptyAs="dash" />
                    </TD>
                    <TD align="right" numeric>
                      <Money amount={c.properties.fatturato_2025} currency="EUR" muted={!Number(c.properties.fatturato_2025)} />
                    </TD>
                    <TD muted numeric>{c.properties.partita_iva || <span className="text-ink-3">–</span>}</TD>
                    <TD muted>{c.properties.domain || <span className="text-ink-3">–</span>}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
            <LoadMoreFooter shown={loaded.length} total={total} hasMore={Boolean(query.hasNextPage)} loading={query.isFetchingNextPage} onMore={() => query.fetchNextPage()} noun="dormant companies" />
          </>
        )}
      </div>
    </div>
  );
}
