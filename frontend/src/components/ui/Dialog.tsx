import { Dialog as RadixDialog } from "radix-ui";
import { X } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export const Dialog = RadixDialog.Root;
export const DialogTrigger = RadixDialog.Trigger;
export const DialogClose = RadixDialog.Close;

export function DialogContent({
  title,
  description,
  children,
  className,
  footer,
}: {
  title: string;
  description?: ReactNode;
  children: ReactNode;
  className?: string;
  footer?: ReactNode;
}) {
  return (
    <RadixDialog.Portal>
      <RadixDialog.Overlay className="fixed inset-0 z-40 bg-ink/40 data-[state=open]:animate-[fade_120ms_ease-out]" />
      <RadixDialog.Content
        className={cn(
          "fixed top-1/2 left-1/2 z-50 w-[calc(100vw-32px)] max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-lg bg-surface shadow-pop focus:outline-none",
          className,
        )}
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div>
            <RadixDialog.Title className="text-[15px] font-semibold text-ink">{title}</RadixDialog.Title>
            {description ? (
              <RadixDialog.Description className="mt-0.5 text-[13px] text-ink-2">{description}</RadixDialog.Description>
            ) : null}
          </div>
          <RadixDialog.Close
            className="rounded-sm p-1 text-ink-3 hover:bg-surface-3 hover:text-ink"
            aria-label="Close"
          >
            <X className="size-4" />
          </RadixDialog.Close>
        </div>
        <div className="px-5 py-4">{children}</div>
        {footer ? <div className="flex items-center justify-end gap-2 border-t border-line px-5 py-3">{footer}</div> : null}
      </RadixDialog.Content>
    </RadixDialog.Portal>
  );
}
