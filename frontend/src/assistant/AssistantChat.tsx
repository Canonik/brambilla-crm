import { useEffect, useRef, useState, type FormEvent } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Paperclip, RefreshCw, Send, ShieldCheck, Square, TriangleAlert, X } from "lucide-react";
import { useAssistant, type ChatMessage } from "./AssistantContext";
import { EvidenceInspector } from "./EvidenceInspector";
import { useCurrentUser } from "@/app/currentUser";
import { Button } from "@/components/ui/Button";
import { Avatar } from "@/components/ui/Avatar";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format";
import type { AgentAttachment } from "@/api/types";

const SUGGESTIONS = [
  "Quanto abbiamo fatturato con Nuova Tessile Spinelli nel 2025?",
  "Segna come vinta la trattativa di Nuova Serramenti Mazza, è arrivato l'ordine firmato.",
  "Quali sono i miei clienti dormienti?",
  "Apri un ticket urgente per Officine Sironi: merce danneggiata.",
];

export function AssistantMark({ className, size = 20 }: { className?: string; size?: number }) {
  return (
    <span
      aria-hidden
      className={cn("inline-flex shrink-0 items-center justify-center rounded-full bg-gentian text-white", className)}
      style={{ width: size, height: size }}
    >
      <span className="block rounded-full bg-signal" style={{ width: size * 0.38, height: size * 0.38 }} />
    </span>
  );
}

function Bubble({ message, onRetry }: { message: ChatMessage; onRetry?: () => void }) {
  const { user } = useCurrentUser();
  const { evidenceEnabled } = useAssistant();
  const mine = message.role === "user";
  return (
    <div className={cn("flex gap-2.5", mine ? "flex-row-reverse" : "flex-row")}>
      {mine ? <Avatar name={user.name} size="sm" className="mt-1" /> : <AssistantMark className="mt-1" size={24} />}
      <div className={cn("min-w-0", !mine && evidenceEnabled && message.evidence ? "w-full max-w-full" : "max-w-[85%]", mine && "text-right")}>
        <div
          className={cn(
            "inline-block max-w-full rounded-lg px-3.5 py-2.5 text-left",
            mine ? "bg-gentian-soft text-ink" : "border border-line bg-surface text-ink",
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
          {!mine && evidenceEnabled && message.evidence ? <EvidenceInspector value={message.evidence} /> : null}
        </div>
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
    </div>
  );
}

function Thinking() {
  return (
    <div className="flex gap-2.5">
      <AssistantMark className="mt-1" size={24} />
      <div className="inline-flex items-center gap-2 rounded-lg border border-line bg-surface px-3.5 py-2.5 text-[13px] text-ink-2" aria-live="polite">
        <span className="flex gap-1" aria-hidden>
          <span className="size-1.5 animate-bounce rounded-full bg-ink-3 [animation-delay:-200ms]" />
          <span className="size-1.5 animate-bounce rounded-full bg-ink-3 [animation-delay:-100ms]" />
          <span className="size-1.5 animate-bounce rounded-full bg-ink-3" />
        </span>
        Working on it
      </div>
    </div>
  );
}

export function AssistantChat({ variant = "panel" }: { variant?: "panel" | "page" }) {
  const { messages, pending, send, retry, reset, cancel, draft, setDraft, evidenceEnabled, setEvidenceEnabled } = useAssistant();
  const { user } = useCurrentUser();
  const [text, setText] = useState("");
  const [attachments, setAttachments] = useState<AgentAttachment[]>([]);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, pending]);

  useEffect(() => {
    if (draft === null) return;
    setText(draft);
    setDraft(null);
    window.setTimeout(() => inputRef.current?.focus(), 50);
  }, [draft, setDraft]);

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

  return (
    <div className={cn("flex h-full min-h-0 flex-col", variant === "page" && "mx-auto w-full max-w-3xl")}>
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-line bg-surface/80 px-4 py-2">
        <div className="flex min-w-0 items-center gap-2 text-[11px] text-ink-2">
          <ShieldCheck className="size-3.5 shrink-0 text-gentian" aria-hidden />
          <span className="truncate">Assistant Insights <span className="text-ink-3">· observable CRM evidence</span></span>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={evidenceEnabled}
          onClick={() => setEvidenceEnabled(!evidenceEnabled)}
          className="inline-flex shrink-0 items-center gap-2 text-[11px] font-medium text-ink-2"
        >
          Show reasoning evidence
          <span className={cn("relative h-5 w-9 rounded-full transition-colors", evidenceEnabled ? "bg-gentian" : "bg-line-strong")}>
            <span className={cn("absolute top-0.5 size-4 rounded-full bg-white shadow-sm transition-transform", evidenceEnabled ? "translate-x-[18px]" : "translate-x-0.5")} />
          </span>
        </button>
      </div>
      <div ref={listRef} className="min-h-0 flex-1 overflow-y-auto scroll-quiet px-4 py-4">
        {messages.length === 0 ? (
          <div className={cn("flex h-full flex-col justify-end gap-4", variant === "page" && "justify-center")}>
            <div className="flex items-start gap-3">
              <AssistantMark size={32} />
              <div>
                <p className="text-[15px] font-semibold text-ink">Ask the CRM</p>
                <p className="mt-0.5 max-w-md text-[13px] text-ink-2">
                  Write what you need the way you would write it to a colleague. The assistant reads and updates the same records you see here, and answers in Italian.
                </p>
              </div>
            </div>
            <ul className="grid gap-1.5">
              {SUGGESTIONS.map((s) => (
                <li key={s}>
                  <button
                    type="button"
                    onClick={() => {
                      setText(s);
                      inputRef.current?.focus();
                    }}
                    className="w-full rounded-md border border-line bg-surface px-3 py-2 text-left text-[13px] text-ink hover:border-gentian-line hover:bg-gentian-soft/50"
                  >
                    {s}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <div className="space-y-4">
            {messages.map((m, i) => (
              <Bubble key={m.id} message={m} onRetry={m.failed && i === messages.length - 1 ? retry : undefined} />
            ))}
            {pending ? <Thinking /> : null}
          </div>
        )}
      </div>

      <form onSubmit={submit} className="border-t border-line bg-surface px-3 py-3">
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
        <div className="flex items-end gap-2 rounded-lg border border-line-strong bg-surface p-1.5 focus-within:border-gentian focus-within:ring-2 focus-within:ring-gentian/20">
          <textarea
            ref={inputRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void submit();
              }
            }}
            rows={Math.min(5, Math.max(1, text.split("\n").length))}
            placeholder={`Message as ${user.name}…`}
            aria-label="Message to the assistant"
            className="max-h-40 min-h-8 flex-1 resize-none bg-transparent px-2 py-1.5 text-[14px] leading-relaxed text-ink placeholder:text-ink-3 focus:outline-none"
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
        <div className="mt-1.5 flex items-center justify-between px-1 text-[11.5px] text-ink-3">
          <span>Enter to send · Shift+Enter for a new line · attach Sinergia-style CSV files</span>
          {messages.length ? (
            <button type="button" onClick={reset} className="hover:text-ink">
              New conversation
            </button>
          ) : null}
        </div>
      </form>
    </div>
  );
}
