import { useState, type ReactNode } from "react";
import { Calendar, CheckSquare, Mail, Phone, StickyNote } from "lucide-react";
import type { Activity } from "@/api/types";
import { useCreateNote } from "@/api/hooks";
import { useCurrentUser } from "@/app/currentUser";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/Input";
import { EmptyState, ErrorState, InlineError } from "@/components/ui/States";
import { SkeletonBlock } from "@/components/ui/Skeleton";
import { Avatar } from "@/components/ui/Avatar";
import { userName } from "@/api/users";
import { formatDate, formatDateTime, formatRelative, parseHsDate } from "@/lib/format";
import { cn } from "@/lib/cn";
import { useToast } from "@/components/ui/Toaster";

const KIND_META: Record<Activity["kind"], { label: string; icon: ReactNode }> = {
  notes: { label: "Note", icon: <StickyNote className="size-3.5" /> },
  calls: { label: "Call", icon: <Phone className="size-3.5" /> },
  emails: { label: "Email", icon: <Mail className="size-3.5" /> },
  meetings: { label: "Meeting", icon: <Calendar className="size-3.5" /> },
  tasks: { label: "Task", icon: <CheckSquare className="size-3.5" /> },
};

function monthKey(ts: string | null) {
  const d = parseHsDate(ts);
  if (!d) return "Undated";
  return new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric", timeZone: "UTC" }).format(d);
}

export function ActivityFeed({
  activities,
  isLoading,
  error,
  onRetry,
  filter,
  limit = 40,
}: {
  activities: Activity[] | undefined;
  isLoading: boolean;
  error?: unknown;
  onRetry?: () => void;
  filter?: Activity["kind"] | "all";
  limit?: number;
}) {
  const [shown, setShown] = useState(limit);
  if (isLoading) return <SkeletonBlock lines={6} className="p-4" />;
  if (error) return <ErrorState error={error} onRetry={onRetry} compact title="Could not load the history" />;
  const list = (activities ?? []).filter((a) => !filter || filter === "all" || a.kind === filter);
  if (list.length === 0) {
    return <EmptyState compact title="No activity yet" description="Notes, calls, emails and meetings logged on this record show up here." />;
  }
  const visible = list.slice(0, shown);
  let lastMonth = "";
  return (
    <div>
      <ol className="relative">
        {visible.map((a) => {
          const m = monthKey(a.timestamp);
          const showMonth = m !== lastMonth;
          lastMonth = m;
          const meta = KIND_META[a.kind];
          return (
            <li key={a.id}>
              {showMonth ? (
                <div className="sticky top-0 z-[1] bg-surface px-4 pt-3 pb-1 text-[11.5px] font-medium text-ink-3">{m}</div>
              ) : null}
              <article className="flex gap-3 px-4 py-2.5">
                <div className="flex w-5 shrink-0 flex-col items-center">
                  <span className="mt-0.5 inline-flex size-5 items-center justify-center rounded-full bg-surface-3 text-ink-2">{meta.icon}</span>
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-[12px] text-ink-2">
                    <span className="font-medium text-ink">{meta.label}</span>
                    {a.title ? <span className="text-ink">{a.title}</span> : null}
                    {a.author ? (
                      <span className="inline-flex items-center gap-1">
                        <Avatar name={userName(a.author)} size="xs" />
                        {userName(a.author)}
                      </span>
                    ) : null}
                    <time className="ml-auto text-ink-3 tnum" dateTime={a.timestamp ?? undefined} title={formatDateTime(a.timestamp)}>
                      {formatDate(a.timestamp)} · {formatRelative(a.timestamp)}
                    </time>
                  </div>
                  {a.body ? <p className="mt-1 text-[13px] leading-relaxed whitespace-pre-line text-ink">{a.body}</p> : null}
                  {a.status ? <p className={cn("mt-1 text-[12px]", a.status === "COMPLETED" ? "text-good" : "text-ink-2")}>{a.status === "COMPLETED" ? "Completed" : a.status === "NOT_STARTED" ? "Not started" : a.status}</p> : null}
                </div>
              </article>
            </li>
          );
        })}
      </ol>
      {list.length > shown ? (
        <div className="px-4 py-3">
          <Button variant="ghost" size="sm" onClick={() => setShown((s) => s + limit)}>
            Show {Math.min(limit, list.length - shown)} more of {list.length - shown}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

export function NoteComposer({ target }: { target: { type: "companies" | "contacts" | "deals" | "tickets"; id: string } }) {
  const [text, setText] = useState("");
  const { user } = useCurrentUser();
  const toast = useToast();
  const mutation = useCreateNote(() => {
    setText("");
    toast.success("Note added");
  });
  return (
    <form
      className="border-b border-line bg-surface-2 px-4 py-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (!text.trim()) return;
        mutation.mutate({ body: text.trim(), author: user.email, target });
      }}
    >
      <Textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Add a note"
        className="min-h-14 bg-surface"
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === "Enter") e.currentTarget.form?.requestSubmit();
        }}
      />
      {mutation.error ? <InlineError error={mutation.error} className="mt-2" /> : null}
      <div className="mt-2 flex items-center justify-between gap-2 text-[12px] text-ink-3">
        <span>Logged as {user.name}</span>
        <Button type="submit" variant="primary" size="sm" loading={mutation.isPending} disabled={!text.trim()}>
          Add note
        </Button>
      </div>
    </form>
  );
}
