import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AnimatePresence, motion } from "motion/react";
import { ArrowUpRight, Building2, CircleAlert, CircleCheck, Kanban, LifeBuoy, Paperclip, RefreshCw, Send, ShieldCheck, Square, TriangleAlert, User, X } from "lucide-react";
import { useAssistant, type ChatMessage } from "./AssistantContext";
import { AssistantMark } from "./AssistantMark";
import { EvidenceInspector } from "./EvidenceInspector";
import { evidenceRecordLink, projectEvidence, type ProjectedEvidenceEvent } from "./evidence";
import * as api from "@/api/endpoints";
import type { AgentAttachment, Company, Contact, Deal, EvidenceRecord, Ticket } from "@/api/types";
import { useCurrentUser } from "@/app/currentUser";
import { Button } from "@/components/ui/Button";
import { Avatar } from "@/components/ui/Avatar";
import { EASE_OUT } from "@/components/motion/primitives";
import { cn } from "@/lib/cn";
import { formatDateTime, fullName } from "@/lib/format";

// ---------- suggestions grounded in the live CRM ----------

export interface Suggestion {
  /** What the assistant can do, in the interface language. */
  label: string;
  /** The message itself, in the assistant's language. */
  prompt: string;
  kind: "read" | "write";
}

export function useSuggestions(): Suggestion[] {
  const top = useQuery({ queryKey: ["suggest", "top-companies"], queryFn: () => api.topCompanies(3), staleTime: 10 * 60_000 });
  const recent = useQuery({ queryKey: ["suggest", "recent-deals"], queryFn: () => api.recentDeals(6), staleTime: 10 * 60_000 });
  return useMemo(() => {
    const companies = top.data?.results ?? [];
    const first = companies[0]?.properties.name;
    const second = companies[1]?.properties.name;
    const deal = (recent.data?.results ?? []).find((d) => d.properties.dealname && d.properties.dealstage !== "closedwon" && d.properties.dealstage !== "closedlost")?.properties.dealname;
    const out: Suggestion[] = [];
    if (first) out.push({ label: "Revenue of a top customer", prompt: `Quanto abbiamo fatturato con ${first} nel 2025?`, kind: "read" });
    out.push({ label: "My dormant customers", prompt: "Quali sono i miei clienti dormienti? Dammi i primi dieci con l'ultima trattativa vinta.", kind: "read" });
    out.push({ label: "Urgent tickets still open", prompt: "Quali ticket urgenti sono ancora aperti e a chi sono assegnati?", kind: "read" });
    if (deal) out.push({ label: "What a deal needs to close", prompt: `Riassumi la trattativa "${deal}" e dimmi cosa manca per chiuderla.`, kind: "read" });
    if (second) out.push({ label: "Log a note on a company", prompt: `Aggiungi una nota a ${second}: chiamare lunedì per il rinnovo del contratto.`, kind: "write" });
    out.push({ label: "Plan the day", prompt: "Cosa devo fare oggi? Trattative in chiusura, ticket urgenti e clienti da richiamare.", kind: "read" });
    return out;
  }, [top.data, recent.data]);
}

export function SuggestionChips({ className, compact, tone = "light", limit }: { className?: string; compact?: boolean; tone?: "light" | "dark"; limit?: number }) {
  const suggestions = useSuggestions().slice(0, limit ?? 99);
  const dark = tone === "dark";
  const { setDraft } = useAssistant();
  return (
    <ul className={cn("grid gap-1.5", compact ? "grid-cols-1" : "sm:grid-cols-2", className)} aria-label="Suggested requests">
      {suggestions.map((s) => (
        <li key={s.prompt}>
          <button
            type="button"
            onClick={() => setDraft(s.prompt)}
            className={cn("group flex w-full items-start gap-2.5 rounded-md border px-3 py-2 text-left transition-colors", dark ? "border-white/15 bg-white/5 hover:border-white/30 hover:bg-white/10" : "border-line bg-surface-2 hover:border-gentian-line hover:bg-gentian-soft/50")}
          >
            <span className={cn("mt-[7px] size-1.5 shrink-0 rounded-full", s.kind === "write" ? "bg-signal" : "bg-gentian")} aria-hidden />
            <span className="min-w-0">
              <span className={cn("block text-[11.5px]", dark ? "text-white/50" : "text-ink-3")}>{s.label}{s.kind === "write" ? " · changes the CRM" : ""}</span>
              <span className={cn("block text-[13px] leading-snug", dark ? "text-white" : "text-ink")}>{s.prompt}</span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

// ---------- composer ----------

export function Composer({ size = "md", autoFocus, className, tone = "light" }: { size?: "md" | "lg"; autoFocus?: boolean; className?: string; tone?: "light" | "dark" }) {
  const { pending, send, cancel, draft, setDraft, messages, reset } = useAssistant();
  const { user } = useCurrentUser();
  const [text, setText] = useState("");
  const [attachments, setAttachments] = useState<AgentAttachment[]>([]);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (draft === null) return;
    setText(draft);
    setDraft(null);
    window.setTimeout(() => inputRef.current?.focus(), 50);
  }, [draft, setDraft]);

  useEffect(() => {
    if (autoFocus && window.matchMedia("(pointer: fine)").matches) inputRef.current?.focus();
  }, [autoFocus]);

  const submit = async (e?: FormEvent) => {
    e?.preventDefault();
    if (pending) return;
    const value = text;
    const files = attachments;
    if (!value.trim() && files.length === 0) return;
    setText("");
    setAttachments([]);
    await send(value, files);
    inputRef.current?.focus();
  };

  const onFiles = async (list: FileList | null) => {
    if (!list) return;
    const next: AgentAttachment[] = [];
    for (const f of Array.from(list)) {
      if (f.size > 512 * 1024) continue;
      const content = await f.text();
      next.push({ name: f.name, content_type: f.type || (f.name.endsWith(".csv") ? "text/csv" : "text/plain"), content });
    }
    setAttachments((a) => [...a, ...next]);
    if (fileRef.current) fileRef.current.value = "";
  };

  const lg = size === "lg";
  return (
    <form onSubmit={submit} className={cn(className)}>
      {attachments.length ? (
        <ul className="mb-2 flex flex-wrap gap-1.5">
          {attachments.map((a) => (
            <li key={a.name} className="inline-flex items-center gap-1 rounded-sm border border-line bg-surface-2 px-1.5 py-0.5 text-[12px] text-ink-2">
              <Paperclip className="size-3" aria-hidden />
              {a.name}
              <button type="button" aria-label={`Remove ${a.name}`} onClick={() => setAttachments((l) => l.filter((x) => x !== a))} className="ml-0.5 text-ink-3 hover:text-ink">
                <X className="size-3" />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <div
        className={cn(
          "flex items-end gap-2 rounded-lg border transition-[border-color,box-shadow] focus-within:ring-2",
          tone === "dark" ? "border-white/20 bg-white/5 text-white focus-within:border-white/50 focus-within:ring-white/15 [&_button]:text-white [&_textarea]:text-white [&_textarea]:placeholder:text-white/40" : "bg-surface focus-within:border-gentian focus-within:ring-gentian/20",
          lg ? "border-line-strong p-2 shadow-card" : "border-line-strong p-1.5",
        )}
      >
        {lg ? <AssistantMark size={28} working={pending} className="mb-1 ml-1" /> : null}
        <textarea
          ref={inputRef}
          data-composer
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void submit();
            }
          }}
          rows={Math.min(6, Math.max(lg ? 2 : 1, text.split("\n").length))}
          placeholder={lg ? "Ask about customers, deals or tickets…" : `Message as ${user.name}…`}
          aria-label="Message to the assistant"
          className={cn(
            "max-h-48 flex-1 resize-none bg-transparent px-2 py-1.5 leading-relaxed text-ink placeholder:text-ink-3 focus:outline-none",
            lg ? "min-h-12 text-[16px]" : "min-h-8 text-[14px]",
          )}
        />
        <input ref={fileRef} type="file" accept=".csv,.txt,text/csv,text/plain" multiple className="hidden" onChange={(e) => void onFiles(e.target.files)} />
        <Button type="button" variant="ghost" size="icon" aria-label="Attach a CSV file" onClick={() => fileRef.current?.click()} disabled={pending}>
          <Paperclip className="size-4" />
        </Button>
        {pending ? (
          <Button type="button" variant="secondary" size="icon" aria-label="Stop" onClick={cancel}>
            <Square className="size-3.5" />
          </Button>
        ) : (
          <Button type="submit" variant="primary" size="icon" aria-label="Send" disabled={!text.trim() && attachments.length === 0}>
            <Send className="size-4" />
          </Button>
        )}
      </div>
      <div className={cn("mt-1.5 flex items-center justify-between gap-3 px-1 text-[11.5px]", tone === "dark" ? "text-white/45" : "text-ink-3")}>
        <span className="truncate">Enter to send · Shift+Enter for a new line · CSV attachments are read as Sinergia exports</span>
        {messages.length ? (
          <button type="button" onClick={reset} className="shrink-0 hover:text-ink">
            New conversation
          </button>
        ) : null}
      </div>
    </form>
  );
}

// ---------- evidence summary: confirmations and record cards ----------

const RECORD_ICON: Partial<Record<EvidenceRecord["type"], typeof Building2>> = { companies: Building2, contacts: User, deals: Kanban, tickets: LifeBuoy };
const RECORD_NOUN: Partial<Record<EvidenceRecord["type"], string>> = { companies: "Company", contacts: "Contact", deals: "Deal", tickets: "Ticket" };

async function recordLabels(records: EvidenceRecord[]): Promise<Record<string, string>> {
  const out: Record<string, string> = {};
  const byType = new Map<EvidenceRecord["type"], string[]>();
  for (const r of records) byType.set(r.type, [...(byType.get(r.type) ?? []), r.id]);
  await Promise.all(
    Array.from(byType.entries()).map(async ([type, ids]) => {
      try {
        if (type === "companies") for (const c of await api.batchRead<Company>(type, ids, ["name"])) out[`${type}:${c.id}`] = c.properties.name || "";
        else if (type === "contacts") for (const c of await api.batchRead<Contact>(type, ids, ["firstname", "lastname"])) out[`${type}:${c.id}`] = fullName(c.properties.firstname, c.properties.lastname);
        else if (type === "deals") for (const d of await api.batchRead<Deal>(type, ids, ["dealname"])) out[`${type}:${d.id}`] = d.properties.dealname || "";
        else if (type === "tickets") for (const t of await api.batchRead<Ticket>(type, ids, ["subject"])) out[`${type}:${t.id}`] = t.properties.subject || "";
      } catch {
        // a missing label falls back to the record id
      }
    }),
  );
  return out;
}

function RecordChips({ records }: { records: EvidenceRecord[] }) {
  const key = records.map((r) => `${r.type}:${r.id}`).join(",");
  const labels = useQuery({ queryKey: ["record-labels", key], queryFn: () => recordLabels(records), staleTime: 5 * 60_000 });
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="Records in this reply">
      {records.map((r) => {
        const href = evidenceRecordLink(r);
        const Icon = RECORD_ICON[r.type] ?? Building2;
        const label = labels.data?.[`${r.type}:${r.id}`] || `${RECORD_NOUN[r.type] ?? r.type} #${r.id}`;
        const body = (
          <>
            <Icon className="size-3.5 shrink-0 text-ink-3" aria-hidden />
            <span className="truncate">{label}</span>
            {href ? <ArrowUpRight className="size-3 shrink-0 text-ink-3 opacity-0 transition-opacity group-hover:opacity-100" aria-hidden /> : null}
          </>
        );
        const cls = "group inline-flex max-w-[260px] items-center gap-1.5 rounded-md border border-line bg-surface px-2 py-1 text-[12.5px] font-medium text-ink";
        return (
          <motion.li key={`${r.type}:${r.id}`} initial={{ opacity: 0, scale: 0.85 }} animate={{ opacity: 1, scale: 1 }} transition={{ type: "spring", stiffness: 500, damping: 28, delay: 0.15 }}>
            {href ? (
              <Link to={href} className={cn(cls, "transition-colors hover:border-gentian-line hover:bg-gentian-soft/60")} title={`${RECORD_NOUN[r.type] ?? r.type} ${r.id}`}>
                {body}
              </Link>
            ) : (
              <span className={cls}>{body}</span>
            )}
          </motion.li>
        );
      })}
    </ul>
  );
}

export function EvidencePanel({ message }: { message: ChatMessage }) {
  if (!message.evidence) return null;
  return (
    <motion.div initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.26, ease: EASE_OUT }} className="flex flex-col gap-2">
      <EvidenceSummary message={message} />
      <EvidenceInspector value={message.evidence} />
    </motion.div>
  );
}

function EvidenceSummary({ message }: { message: ChatMessage }) {
  const evidence = useMemo(() => projectEvidence(message.evidence), [message.evidence]);
  const summary = useMemo(() => {
    if (!evidence) return null;
    const latest = new Map<number, ProjectedEvidenceEvent>();
    for (const e of evidence.events) latest.set(e.call, e);
    const writes = Array.from(latest.values()).filter((e) => e.operation === "write");
    const done = writes.filter((e) => e.status === "committed").map((e) => e.label);
    const undone = writes.filter((e) => e.status === "rolled_back" || e.status === "unknown" || e.status === "awaiting_commit");
    const seen = new Set<string>();
    const records: EvidenceRecord[] = [];
    for (const e of evidence.events) for (const r of e.records) {
      const k = `${r.type}:${r.id}`;
      if (!seen.has(k) && evidenceRecordLink(r)) {
        seen.add(k);
        records.push(r);
      }
    }
    const steps = Array.from(new Set(evidence.events.map((e) => e.label))).slice(0, 5);
    return { done, undone, steps, records: records.slice(0, 3), more: Math.max(0, records.length - 3) };
  }, [evidence]);
  if (!summary || (!summary.done.length && !summary.undone.length && !summary.records.length && !summary.steps.length)) return null;
  return (
    <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.24, ease: EASE_OUT, delay: 0.1 }} className="mt-2 flex flex-col gap-2">
      {summary.steps.length ? (
        <motion.ol initial="hidden" animate="show" variants={{ hidden: {}, show: { transition: { staggerChildren: 0.06 } } }} className="flex flex-col gap-1" aria-label="What the CRM did">
          {summary.steps.map((label) => (
            <motion.li key={label} variants={{ hidden: { opacity: 0, x: -6 }, show: { opacity: 1, x: 0, transition: { duration: 0.2, ease: EASE_OUT } } }} className="flex items-center gap-2 text-[12.5px] text-ink-2">
              <span className="size-1.5 rounded-full bg-gentian" aria-hidden />
              {label}
            </motion.li>
          ))}
        </motion.ol>
      ) : null}
      {summary.done.length ? (
        <p className="inline-flex items-start gap-1.5 self-start rounded-md border border-good/30 bg-good-soft px-2.5 py-1.5 text-[12.5px] font-medium text-good">
          <CircleCheck className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          <span>Done and saved: {Array.from(new Set(summary.done)).join(", ").toLowerCase()}</span>
        </p>
      ) : null}
      {summary.undone.length ? (
        <p className="inline-flex items-start gap-1.5 self-start rounded-md border border-warn/40 bg-warn-soft px-2.5 py-1.5 text-[12.5px] font-medium text-warn">
          <CircleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          <span>A change was attempted but not confirmed. Check the record before relying on it.</span>
        </p>
      ) : null}
      {summary.records.length ? (
        <div className="flex flex-wrap items-center gap-1.5">
          <RecordChips records={summary.records} />
          {summary.more ? <span className="text-[12px] text-ink-3">+{summary.more} more in the evidence</span> : null}
        </div>
      ) : null}
    </motion.div>
  );
}

// ---------- thread ----------

function Bubble({ message, onRetry, sideEvidence }: { message: ChatMessage; onRetry?: () => void; sideEvidence?: boolean }) {
  const { user } = useCurrentUser();
  const { evidenceEnabled } = useAssistant();
  const mine = message.role === "user";
  const showEvidence = !mine && !sideEvidence && evidenceEnabled && Boolean(message.evidence);
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.26, ease: EASE_OUT }}
      className={cn("flex gap-2.5", mine ? "flex-row-reverse" : "flex-row")}
    >
      {mine ? <Avatar name={user.name} size="sm" className="mt-1" /> : <AssistantMark className="mt-1" size={24} />}
      <div className={cn("min-w-0", showEvidence ? "w-full max-w-full" : "max-w-[85%]", mine && "text-right")}>
        <div
          className={cn(
            "inline-block max-w-full rounded-lg px-3.5 py-2.5 text-left",
            mine ? "bg-gentian-soft text-ink" : "border border-line bg-surface text-ink shadow-card",
            message.failed && "border-bad/40 bg-bad-soft",
          )}
        >
          {mine ? (
            <p className="whitespace-pre-wrap text-[14px] leading-relaxed">{message.content}</p>
          ) : (
            <div className="prose-chat">
              <Markdown remarkPlugins={[remarkGfm]}>{message.content}</Markdown>
            </div>
          )}
          {message.attachments?.length ? (
            <ul className="mt-2 flex flex-wrap gap-1.5">
              {message.attachments.map((a) => (
                <li key={a.name} className="inline-flex items-center gap-1 rounded-sm border border-line bg-surface px-1.5 py-0.5 text-[11.5px] text-ink-2">
                  <Paperclip className="size-3" aria-hidden />
                  {a.name}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        {showEvidence ? <EvidenceSummary message={message} /> : null}
        {showEvidence && message.evidence ? <EvidenceInspector value={message.evidence} /> : null}
        <div className={cn("mt-1 flex items-center gap-2 text-[11px] text-ink-3", mine ? "justify-end" : "justify-start")}>
          <time dateTime={message.at}>{formatDateTime(message.at)}</time>
          {message.failed ? (
            <span className="inline-flex items-center gap-1 text-bad">
              <TriangleAlert className="size-3" aria-hidden /> {message.failed}
              {onRetry ? (
                <button type="button" onClick={onRetry} className="ml-1 inline-flex items-center gap-1 font-medium underline underline-offset-2">
                  <RefreshCw className="size-3" aria-hidden /> Retry
                </button>
              ) : null}
            </span>
          ) : null}
        </div>
      </div>
    </motion.div>
  );
}

const WORK_STEPS = ["Reading records", "Checking rules", "Writing the answer"];

function Thinking() {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => setElapsed((n) => n + 1), 1000);
    return () => window.clearInterval(t);
  }, []);
  const step = Math.min(WORK_STEPS.length - 1, Math.floor(elapsed / 3));
  const slow = elapsed >= 20;
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, transition: { duration: 0.12 } }} transition={{ duration: 0.2, ease: EASE_OUT }} className="flex gap-2.5">
      <AssistantMark className="mt-1" size={24} working />
      <div className="rounded-lg border border-line bg-surface px-3.5 py-2.5 text-[13px] text-ink-2" role="status" aria-live="polite">
        <div className="flex items-center gap-2 font-medium text-ink">
          Reading the CRM
          <span className="flex gap-1" aria-hidden>
            {[0, 1, 2].map((i) => (
              <span key={i} className="size-1.5 animate-bounce rounded-full bg-gentian" style={{ animationDelay: `${i * 120}ms` }} />
            ))}
          </span>
          <span className="tnum text-[12px] font-normal text-ink-3">{elapsed}s</span>
        </div>
        <ol className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px]">
          {WORK_STEPS.map((label, i) => (
            <li key={label} className={cn("inline-flex items-center gap-1.5", i < step ? "text-ink-2" : i === step ? "text-gentian" : "text-ink-3")}>
              <span className={cn("size-1.5 rounded-full", i <= step ? "bg-gentian" : "bg-line-strong", i === step && "mark-working")} aria-hidden />
              {label}
            </li>
          ))}
        </ol>
        {slow ? <p className="mt-1.5 text-[12px] text-ink-3">This one needs several lookups. The assistant has up to a minute.</p> : null}
      </div>
    </motion.div>
  );
}

function EvidenceSwitch() {
  const { evidenceEnabled, setEvidenceEnabled } = useAssistant();
  return (
    <div className="flex shrink-0 items-center justify-between gap-3 border-b border-line bg-surface/80 px-4 py-2">
      <div className="flex min-w-0 items-center gap-2 text-[11px] text-ink-2">
        <ShieldCheck className="size-3.5 shrink-0 text-gentian" aria-hidden />
        <span className="truncate">
          Assistant Insights <span className="text-ink-3">· see what the CRM did</span>
        </span>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={evidenceEnabled}
        onClick={() => setEvidenceEnabled(!evidenceEnabled)}
        className="group inline-flex shrink-0 items-center gap-2 rounded-md px-1 py-0.5 text-[11.5px] font-medium text-ink-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gentian"
      >
        Show evidence
        <span className={cn("relative inline-block h-5 w-9 shrink-0 rounded-full transition-colors duration-150", evidenceEnabled ? "bg-gentian" : "bg-line-strong")} aria-hidden>
          <span className={cn("absolute top-0.5 left-0.5 block size-4 rounded-full bg-white shadow-sm transition-transform duration-150 ease-out", evidenceEnabled ? "translate-x-4" : "translate-x-0")} />
        </span>
      </button>
    </div>
  );
}

export function EvidenceBadge({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-sm border border-gentian-line bg-gentian-soft px-1.5 py-0.5 text-[11px] font-semibold text-gentian", className)}>
      <ShieldCheck className="size-3" aria-hidden />
      Evidence
    </span>
  );
}

export function AssistantChat({ variant = "panel" }: { variant?: "panel" | "page" | "home" }) {
  const { messages, pending, retry, evidenceEnabled } = useAssistant();
  const side = variant === "page";
  const latest = side && evidenceEnabled ? [...messages].reverse().find((m) => m.role === "assistant" && m.evidence) : undefined;
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [messages, pending]);

  return (
    <div className={cn("flex h-full min-h-0 flex-col", variant === "page" && "mx-auto w-full max-w-6xl")}>
      <EvidenceSwitch />
      <div ref={listRef} className="min-h-0 flex-1 overflow-y-auto scroll-quiet px-4 py-4">
        {messages.length === 0 ? (
          <div className={cn("flex h-full flex-col justify-end gap-4", variant === "page" && "justify-center")}>
            <div className="flex items-start gap-3">
              <AssistantMark size={32} />
              <div>
                <p className="text-[15px] font-semibold text-ink">Ask the CRM</p>
                <p className="mt-0.5 max-w-md text-[13px] text-ink-2">
                  Write what you need the way you would write it to a colleague. The assistant reads and updates the same records you see here, shows what it touched, and answers in Italian.
                </p>
              </div>
            </div>
            <SuggestionChips compact={variant === "panel"} />
          </div>
        ) : (
          <div className={cn(side && "grid gap-4 xl:grid-cols-[minmax(0,1fr)_400px] xl:items-start")}>
            <div className="min-w-0 space-y-4">
              {messages.map((m, i) => (
                <Bubble key={m.id} message={m} sideEvidence={side} onRetry={m.failed && i === messages.length - 1 ? retry : undefined} />
              ))}
              <AnimatePresence>{pending ? <Thinking key="thinking" /> : null}</AnimatePresence>
            </div>
            {latest ? (
              <aside aria-label="Evidence for the latest answer" className="min-w-0 xl:sticky xl:top-0">
                <p className="mb-2 text-[12px] font-medium text-ink-2">Evidence for the latest answer</p>
                <EvidencePanel key={latest.id} message={latest} />
              </aside>
            ) : null}
          </div>
        )}
      </div>
      <Composer size={variant === "panel" ? "md" : "lg"} className="border-t border-line bg-surface px-3 py-3" />
    </div>
  );
}
