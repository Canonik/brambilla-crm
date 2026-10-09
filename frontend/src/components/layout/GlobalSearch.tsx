import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Building2, Kanban, LoaderCircle, Search, User } from "lucide-react";
import { useGlobalSearch } from "@/api/hooks";
import { Kbd } from "@/components/ui/Button";
import { Avatar } from "@/components/ui/Avatar";
import { ClassPlate } from "@/components/crm/ClassPlate";
import { Money } from "@/components/crm/Values";
import { cn } from "@/lib/cn";
import { fullName } from "@/lib/format";
import { useDebounced } from "@/lib/useDebounced";

type Hit = { kind: "company" | "contact" | "deal"; id: string; title: string; sub: string; extra?: React.ReactNode };

export function GlobalSearch({ onNavigate }: { onNavigate?: () => void }) {
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState(0);
  const q = useDebounced(text.trim(), 220);
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const search = useGlobalSearch(q);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const typing = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
      if (e.key === "/" && !typing) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, []);

  const hits: Hit[] = [];
  for (const c of search.data?.companies ?? []) {
    hits.push({
      kind: "company",
      id: c.id,
      title: c.properties.name || "Unnamed company",
      sub: [c.properties.city, c.properties.state].filter(Boolean).join(", ") || c.properties.domain || "",
      extra: <ClassPlate value={c.properties.classe_cliente} size="sm" emptyAs="dash" />,
    });
  }
  for (const c of search.data?.contacts ?? []) {
    hits.push({ kind: "contact", id: c.id, title: fullName(c.properties.firstname, c.properties.lastname), sub: c.properties.email || c.properties.company || "" });
  }
  for (const d of search.data?.deals ?? []) {
    hits.push({
      kind: "deal",
      id: d.id,
      title: d.properties.dealname || "Untitled deal",
      sub: "",
      extra: <Money amount={d.properties.amount} currency={d.properties.deal_currency_code} className="text-[12px] text-ink-2" />,
    });
  }

  useEffect(() => setCursor(0), [q]);

  const go = (hit: Hit) => {
    setOpen(false);
    setText("");
    onNavigate?.();
    navigate(hit.kind === "company" ? `/companies/${hit.id}` : hit.kind === "contact" ? `/contacts/${hit.id}` : `/deals/${hit.id}`);
  };

  const showPanel = open && q.length >= 2;

  return (
    <div ref={rootRef} className="relative px-2">
      <div className="relative">
        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-ink-3" aria-hidden />
        <input
          ref={inputRef}
          type="search"
          role="combobox"
          aria-expanded={showPanel}
          aria-controls="global-search-results"
          aria-label="Search companies, contacts and deals"
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              setOpen(false);
              inputRef.current?.blur();
            } else if (e.key === "ArrowDown") {
              e.preventDefault();
              setCursor((c) => Math.min(hits.length - 1, c + 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setCursor((c) => Math.max(0, c - 1));
            } else if (e.key === "Enter" && hits[cursor]) {
              e.preventDefault();
              go(hits[cursor]!);
            }
          }}
          placeholder="Search"
          className="h-8 w-full rounded-md border border-line bg-surface-2 pl-8 pr-8 text-[13px] text-ink placeholder:text-ink-3 focus:border-gentian focus:bg-surface focus:outline-none focus:ring-2 focus:ring-gentian/20 [&::-webkit-search-cancel-button]:hidden"
        />
        <span className="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2">
          {search.isFetching ? <LoaderCircle className="size-3.5 animate-spin text-ink-3" aria-hidden /> : <Kbd>/</Kbd>}
        </span>
      </div>
      {showPanel ? (
        <div
          id="global-search-results"
          role="listbox"
          className="absolute top-full left-2 right-2 z-40 mt-1 max-h-[70vh] overflow-y-auto rounded-md border border-line bg-surface shadow-pop scroll-quiet md:left-2 md:w-[380px] md:right-auto"
        >
          {search.isPending ? (
            <div className="px-3 py-3 text-[12.5px] text-ink-3">Searching…</div>
          ) : search.isError ? (
            <div className="px-3 py-3 text-[12.5px] text-bad">Search failed. Try again.</div>
          ) : hits.length === 0 ? (
            <div className="px-3 py-3 text-[12.5px] text-ink-3">Nothing matches "{q}".</div>
          ) : (
            (["company", "contact", "deal"] as const).map((kind) => {
              const group = hits.filter((h) => h.kind === kind);
              if (!group.length) return null;
              const Icon = kind === "company" ? Building2 : kind === "contact" ? User : Kanban;
              return (
                <div key={kind} className="py-1">
                  <div className="flex items-center gap-1.5 px-3 py-1 text-[11.5px] font-medium text-ink-3">
                    <Icon className="size-3" aria-hidden />
                    {kind === "company" ? "Companies" : kind === "contact" ? "Contacts" : "Deals"}
                  </div>
                  {group.map((h) => {
                    const idx = hits.indexOf(h);
                    return (
                      <button
                        key={`${h.kind}-${h.id}`}
                        type="button"
                        role="option"
                        aria-selected={idx === cursor}
                        onMouseEnter={() => setCursor(idx)}
                        onClick={() => go(h)}
                        className={cn("flex w-full items-center gap-2.5 px-3 py-1.5 text-left", idx === cursor ? "bg-gentian-soft" : "hover:bg-surface-2")}
                      >
                        {h.kind === "deal" ? (
                          <span className="inline-flex size-6 shrink-0 items-center justify-center rounded-sm bg-surface-3 text-ink-2">
                            <Kanban className="size-3.5" />
                          </span>
                        ) : (
                          <Avatar name={h.title} size="sm" square={h.kind === "company"} />
                        )}
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13px] font-medium text-ink">{h.title}</span>
                          {h.sub ? <span className="block truncate text-[12px] text-ink-3">{h.sub}</span> : null}
                        </span>
                        {h.extra}
                      </button>
                    );
                  })}
                </div>
              );
            })
          )}
        </div>
      ) : null}
    </div>
  );
}
