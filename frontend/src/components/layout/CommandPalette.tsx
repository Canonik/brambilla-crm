import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Dialog as RadixDialog } from "radix-ui";
import { motion } from "motion/react";
import { Building2, CornerDownLeft, Kanban, LayoutDashboard, LifeBuoy, LoaderCircle, MessageSquareText, Moon, Search, Users } from "lucide-react";
import { useGlobalSearch } from "@/api/hooks";
import { useAssistant } from "@/assistant/AssistantContext";
import { AssistantMark } from "@/assistant/AssistantMark";
import { Avatar } from "@/components/ui/Avatar";
import { Kbd } from "@/components/ui/Button";
import { ClassPlate } from "@/components/crm/ClassPlate";
import { Money } from "@/components/crm/Values";
import { EASE_OUT } from "@/components/motion/primitives";
import { cn } from "@/lib/cn";
import { fullName } from "@/lib/format";
import { useDebounced } from "@/lib/useDebounced";

// One box for everything: jump to a page, open a record, or hand the text to
// the assistant. Cmd/Ctrl+K from anywhere, "/" from the sidebar.

type Group = "ask" | "go" | "company" | "contact" | "deal";
interface Item {
  id: string;
  group: Group;
  title: string;
  sub?: string;
  icon: ReactNode;
  extra?: ReactNode;
  run: () => void;
}

const PAGES = [
  { to: "/", label: "Home", hint: "assistant workspace", icon: LayoutDashboard, keywords: "home dashboard assistant workspace start" },
  { to: "/companies", label: "Companies", hint: "customers and prospects", icon: Building2, keywords: "companies customers accounts aziende" },
  { to: "/contacts", label: "Contacts", hint: "people at those companies", icon: Users, keywords: "contacts people contatti" },
  { to: "/deals", label: "Deals", hint: "sales and renewals board", icon: Kanban, keywords: "deals board pipeline kanban trattative" },
  { to: "/dormant", label: "Dormant customers", hint: "won before, silent in 2025", icon: Moon, keywords: "dormant customers list clienti dormienti" },
  { to: "/tickets", label: "Tickets", hint: "support queue", icon: LifeBuoy, keywords: "tickets support assistenza" },
  { to: "/assistant", label: "Assistant", hint: "full-page conversation", icon: MessageSquareText, keywords: "assistant chat ask ai" },
];

const GROUP_LABEL: Record<Group, string> = { ask: "Assistant", go: "Go to", company: "Companies", contact: "Contacts", deal: "Deals" };

export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [text, setText] = useState("");
  const [cursor, setCursor] = useState(0);
  const q = useDebounced(text.trim(), 180);
  const navigate = useNavigate();
  const location = useLocation();
  const assistant = useAssistant();
  const search = useGlobalSearch(q);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) {
      setText("");
      setCursor(0);
    }
  }, [open]);
  useEffect(() => setCursor(0), [q]);

  const close = () => onOpenChange(false);

  const items = useMemo<Item[]>(() => {
    const out: Item[] = [];
    const needle = text.trim().toLowerCase();
    if (needle.length >= 3) {
      out.push({
        id: "ask",
        group: "ask",
        title: text.trim(),
        sub: "Send this to the assistant",
        icon: <AssistantMark size={22} />,
        run: () => {
          close();
          if (location.pathname !== "/" && location.pathname !== "/assistant") assistant.setOpen(true);
          void assistant.send(text.trim());
        },
      });
    }
    for (const p of PAGES) {
      if (needle && !p.label.toLowerCase().includes(needle) && !p.keywords.includes(needle)) continue;
      out.push({
        id: `go:${p.to}`,
        group: "go",
        title: p.label,
        sub: p.hint,
        icon: <span className="inline-flex size-6 items-center justify-center rounded-sm bg-surface-3 text-ink-2"><p.icon className="size-3.5" aria-hidden /></span>,
        run: () => {
          close();
          navigate(p.to);
        },
      });
    }
    for (const c of search.data?.companies ?? []) {
      out.push({
        id: `company:${c.id}`,
        group: "company",
        title: c.properties.name || "Unnamed company",
        sub: [c.properties.city, c.properties.state].filter(Boolean).join(", ") || c.properties.domain || undefined,
        icon: <Avatar name={c.properties.name} size="sm" square />,
        extra: <ClassPlate value={c.properties.classe_cliente} size="sm" emptyAs="dash" />,
        run: () => {
          close();
          navigate(`/companies/${c.id}`);
        },
      });
    }
    for (const c of search.data?.contacts ?? []) {
      const name = fullName(c.properties.firstname, c.properties.lastname);
      out.push({
        id: `contact:${c.id}`,
        group: "contact",
        title: name,
        sub: c.properties.email || c.properties.company || undefined,
        icon: <Avatar name={name} size="sm" />,
        run: () => {
          close();
          navigate(`/contacts/${c.id}`);
        },
      });
    }
    for (const d of search.data?.deals ?? []) {
      out.push({
        id: `deal:${d.id}`,
        group: "deal",
        title: d.properties.dealname || "Untitled deal",
        icon: <span className="inline-flex size-6 items-center justify-center rounded-sm bg-surface-3 text-ink-2"><Kanban className="size-3.5" aria-hidden /></span>,
        extra: <Money amount={d.properties.amount} currency={d.properties.deal_currency_code} className="text-[12px] text-ink-2" />,
        run: () => {
          close();
          navigate(`/deals/${d.id}`);
        },
      });
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, search.data, location.pathname, assistant.send, assistant.setOpen, navigate]);

  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>(`[data-index="${cursor}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => Math.min(items.length - 1, c + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => Math.max(0, c - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      items[cursor]?.run();
    }
  };

  const searching = q.length >= 2 && search.isFetching;
  const groups = (["ask", "go", "company", "contact", "deal"] as Group[]).map((g) => ({ g, rows: items.filter((i) => i.group === g) })).filter((x) => x.rows.length);

  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="fixed inset-0 z-40 bg-ink/30" />
        <RadixDialog.Content
          aria-label="Search or ask"
          className="fixed top-[10vh] left-1/2 z-50 w-[min(640px,calc(100vw-24px))] -translate-x-1/2 focus:outline-none"
          onOpenAutoFocus={(e) => {
            e.preventDefault();
            (e.currentTarget as HTMLElement).querySelector("input")?.focus();
          }}
        >
          <RadixDialog.Title className="sr-only">Search or ask the assistant</RadixDialog.Title>
          <RadixDialog.Description className="sr-only">Type to find a page or a record, or write a question for the assistant.</RadixDialog.Description>
          <motion.div
            initial={{ opacity: 0, scale: 0.98, y: -6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{ duration: 0.16, ease: EASE_OUT }}
            className="overflow-hidden rounded-lg border border-line bg-surface shadow-pop"
          >
            <div className="flex items-center gap-2.5 border-b border-line px-3">
              <Search className="size-4 shrink-0 text-ink-3" aria-hidden />
              <input
                type="text"
                role="combobox"
                aria-expanded
                aria-controls="palette-list"
                aria-activedescendant={items[cursor] ? `palette-${items[cursor].id}` : undefined}
                aria-label="Search or ask"
                autoComplete="off"
                spellCheck={false}
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder="Find a company, contact, deal or page, or ask the assistant"
                className="h-12 min-w-0 flex-1 bg-transparent text-[15px] text-ink placeholder:text-ink-3 focus:outline-none"
              />
              {searching ? <LoaderCircle className="size-4 animate-spin text-ink-3" aria-hidden /> : <Kbd>Esc</Kbd>}
            </div>
            <div ref={listRef} id="palette-list" role="listbox" className="max-h-[min(60vh,440px)] overflow-y-auto scroll-quiet py-1">
              {groups.length === 0 ? (
                <p className="px-4 py-6 text-center text-[13px] text-ink-3">{q.length >= 2 && !search.isPending ? `Nothing matches "${q}".` : "Keep typing."}</p>
              ) : (
                groups.map(({ g, rows }) => (
                  <div key={g} className="py-1">
                    <div className="px-3 pb-1 pt-1.5 text-[11.5px] font-medium text-ink-3">{GROUP_LABEL[g]}</div>
                    {rows.map((item) => {
                      const idx = items.indexOf(item);
                      const selected = idx === cursor;
                      return (
                        <button
                          key={item.id}
                          id={`palette-${item.id}`}
                          data-index={idx}
                          type="button"
                          role="option"
                          aria-selected={selected}
                          onMouseEnter={() => setCursor(idx)}
                          onClick={item.run}
                          className={cn("flex w-full items-center gap-3 px-3 py-2 text-left", selected ? "bg-gentian-soft" : "hover:bg-surface-2")}
                        >
                          {item.icon}
                          <span className="min-w-0 flex-1">
                            <span className={cn("block truncate text-[13.5px] font-medium", g === "ask" ? "text-gentian" : "text-ink")}>{g === "ask" ? `Ask: ${item.title}` : item.title}</span>
                            {item.sub ? <span className="block truncate text-[12px] text-ink-3">{item.sub}</span> : null}
                          </span>
                          {item.extra}
                          {selected ? <CornerDownLeft className="size-3.5 shrink-0 text-ink-3" aria-hidden /> : null}
                        </button>
                      );
                    })}
                  </div>
                ))
              )}
            </div>
            <div className="flex items-center gap-3 border-t border-line bg-surface-2 px-3 py-1.5 text-[11.5px] text-ink-3">
              <span className="inline-flex items-center gap-1"><Kbd>↑</Kbd><Kbd>↓</Kbd> move</span>
              <span className="inline-flex items-center gap-1"><Kbd>↵</Kbd> open</span>
              <span className="ml-auto hidden sm:inline">Three letters or more become a question for the assistant</span>
            </div>
          </motion.div>
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}

export function PaletteTrigger({ onOpen, className }: { onOpen: () => void; className?: string }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className={cn(
        "flex h-8 w-full items-center gap-2 rounded-md border border-line bg-surface-2 px-2.5 text-left text-[13px] text-ink-3 transition-colors hover:border-line-strong hover:bg-surface hover:text-ink-2",
        className,
      )}
    >
      <Search className="size-3.5 shrink-0" aria-hidden />
      <span className="flex-1 truncate">Search or ask</span>
      <Kbd>⌘K</Kbd>
    </button>
  );
}
