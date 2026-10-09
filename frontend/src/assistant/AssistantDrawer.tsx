import { useEffect } from "react";
import { Link } from "react-router-dom";
import { Maximize2, X } from "lucide-react";
import { useAssistant } from "./AssistantContext";
import { AssistantChat } from "./AssistantChat";
import { AssistantMark } from "./AssistantMark";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";

export function AssistantDrawer() {
  const { open, setOpen } = useAssistant();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, setOpen]);

  return (
    <aside
      aria-label="Assistant"
      aria-hidden={!open}
      className={cn(
        "fixed inset-y-0 right-0 z-30 flex w-[min(440px,100vw)] flex-col border-l border-line bg-paper shadow-pop transition-transform duration-200 ease-out",
        open ? "translate-x-0" : "translate-x-full",
      )}
    >
      <div className="flex h-12 shrink-0 items-center justify-between gap-2 border-b border-line bg-surface px-3">
        <div className="flex items-center gap-2">
          <AssistantMark size={20} />
          <span className="text-[13.5px] font-semibold text-ink">Assistant</span>
        </div>
        <div className="flex items-center gap-1">
          <Link
            to="/assistant"
            aria-label="Open full page"
            onClick={() => setOpen(false)}
            className="inline-flex size-8 items-center justify-center rounded-md text-ink-2 hover:bg-surface-3 hover:text-ink"
          >
            <Maximize2 className="size-4" />
          </Link>
          <Button variant="ghost" size="icon" aria-label="Close assistant" onClick={() => setOpen(false)}>
            <X className="size-4" />
          </Button>
        </div>
      </div>
      <div className="min-h-0 flex-1">{open ? <AssistantChat variant="panel" /> : null}</div>
    </aside>
  );
}
