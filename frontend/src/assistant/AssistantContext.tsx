import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { askAssistant } from "@/api/endpoints";
import type { AgentAttachment, AgentMessage, AssistantEvidence } from "@/api/types";
import { useCurrentUser } from "@/app/currentUser";
import { errorMessage } from "@/components/ui/States";

// One conversation shared by the side panel and the full page. The backend
// keeps no state, so every turn sends the whole history (the contract in the
// brief), and the history itself lives here, persisted for the session.

export interface ChatMessage extends AgentMessage {
  id: string;
  at: string;
  evidence?: AssistantEvidence;
  /** Set when the turn failed; the message is kept so the user can retry. */
  failed?: string;
}

interface AssistantApi {
  messages: ChatMessage[];
  pending: boolean;
  error: string | null;
  evidenceEnabled: boolean;
  setEvidenceEnabled: (enabled: boolean) => void;
  open: boolean;
  setOpen: (open: boolean) => void;
  toggle: () => void;
  /** Text waiting to be placed in the composer (from "Ask about this…" buttons). */
  draft: string | null;
  setDraft: (text: string | null) => void;
  /** Open the panel with a prefilled question. */
  ask: (text: string) => void;
  send: (text: string, attachments?: AgentAttachment[]) => Promise<void>;
  retry: () => Promise<void>;
  reset: () => void;
  cancel: () => void;
}

const Ctx = createContext<AssistantApi | null>(null);
const STORAGE_KEY = "brambilla.crm.assistant";

function nowIso(): string {
  const d = new Date();
  const off = -d.getTimezoneOffset();
  const sign = off >= 0 ? "+" : "-";
  const pad = (n: number) => String(Math.abs(n)).padStart(2, "0");
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 19);
  return `${local}${sign}${pad(Math.floor(off / 60))}:${pad(off % 60)}`;
}

function load(): ChatMessage[] {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed.map(({ evidence: _evidence, trace: _trace, ...message }) => message as ChatMessage);
  } catch {
    return [];
  }
}

export function AssistantProvider({ children }: { children: ReactNode }) {
  const { user } = useCurrentUser();
  const [messages, setMessages] = useState<ChatMessage[]>(load);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [evidenceEnabled, setEvidenceEnabledState] = useState(false);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const requestRef = useRef(0);

  useEffect(() => {
    try {
      const safe = messages.map(({ evidence: _evidence, ...message }) => message);
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(safe));
    } catch {
      // ignore
    }
  }, [messages]);

  const run = useCallback(
    async (history: ChatMessage[]) => {
      abortRef.current?.abort();
      const requestId = ++requestRef.current;
      const controller = new AbortController();
      abortRef.current = controller;
      setPending(true);
      setError(null);
      try {
        const res = await askAssistant(
          {
            context: { now: nowIso(), user: user.email },
            messages: history
              .filter((m) => !m.failed)
              .map(({ role, content, attachments }) => (attachments?.length ? { role, content, attachments } : { role, content })),
          },
          controller.signal,
          evidenceEnabled,
        );
        if (requestRef.current !== requestId) return;
        const reply: ChatMessage = {
          id: `a-${Date.now()}`,
          role: "assistant",
          content: typeof res?.reply === "string" && res.reply.trim() ? res.reply : "(The assistant sent an empty reply.)",
          at: new Date().toISOString(),
          evidence: res?.trace,
        };
        setMessages((m) => [...m, reply]);
      } catch (err) {
        if (requestRef.current !== requestId) return;
        if (err instanceof DOMException && err.name === "AbortError") return;
        const msg = errorMessage(err);
        setError(msg);
        setMessages((m) => m.map((x, i) => (i === m.length - 1 && x.role === "user" ? { ...x, failed: msg } : x)));
      } finally {
        if (abortRef.current === controller && requestRef.current === requestId) {
          abortRef.current = null;
          setPending(false);
        }
      }
    },
    [evidenceEnabled, user.email],
  );

  const send = useCallback(
    async (text: string, attachments?: AgentAttachment[]) => {
      const content = text.trim();
      if (!content && !attachments?.length) return;
      const msg: ChatMessage = {
        id: `u-${Date.now()}`,
        role: "user",
        content,
        at: new Date().toISOString(),
        ...(attachments?.length ? { attachments } : {}),
      };
      const next = [...messages.filter((m) => !m.failed), msg];
      setMessages(next);
      await run(next);
    },
    [messages, run],
  );

  const retry = useCallback(async () => {
    const next = messages.map((m) => ({ ...m, failed: undefined }));
    setMessages(next);
    await run(next);
  }, [messages, run]);

  const reset = useCallback(() => {
    requestRef.current += 1;
    abortRef.current?.abort();
    setMessages([]);
    setError(null);
    setPending(false);
  }, []);

  const cancel = useCallback(() => {
    requestRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    setPending(false);
    setMessages((m) => m.map((x, i) => (i === m.length - 1 && x.role === "user" ? { ...x, failed: "Cancelled" } : x)));
  }, []);

  const setEvidenceEnabled = useCallback((enabled: boolean) => {
    setEvidenceEnabledState(enabled);
    if (!enabled) setMessages((current) => current.map(({ evidence: _evidence, ...message }) => message));
  }, []);

  const api = useMemo<AssistantApi>(
    () => ({
      messages,
      pending,
      error,
      evidenceEnabled,
      setEvidenceEnabled,
      open,
      setOpen,
      toggle: () => setOpen((o) => !o),
      draft,
      setDraft,
      ask: (text: string) => {
        setDraft(text);
        setOpen(true);
      },
      send,
      retry,
      reset,
      cancel,
    }),
    [messages, pending, error, evidenceEnabled, open, draft, send, retry, reset, cancel, setEvidenceEnabled],
  );

  return <Ctx.Provider value={api}>{children}</Ctx.Provider>;
}

export function useAssistant() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAssistant must be used inside AssistantProvider");
  return ctx;
}
