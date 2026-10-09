import { Tabs as RadixTabs } from "radix-ui";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export const Tabs = RadixTabs.Root;
export const TabsContent = RadixTabs.Content;

export function TabsList({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <RadixTabs.List className={cn("flex items-end gap-0.5 overflow-x-auto scroll-quiet border-b border-line", className)}>{children}</RadixTabs.List>
  );
}

export function TabsTrigger({
  value,
  children,
  count,
}: {
  value: string;
  children: ReactNode;
  count?: number | string;
}) {
  return (
    <RadixTabs.Trigger
      value={value}
      className={cn(
        "-mb-px inline-flex h-9 shrink-0 items-center gap-1.5 border-b-2 border-transparent px-3 text-[13px] font-medium text-ink-2",
        "hover:text-ink data-[state=active]:border-gentian data-[state=active]:text-ink transition-colors",
      )}
    >
      {children}
      {count !== undefined ? (
        <span className="rounded-sm bg-surface-3 px-1.5 py-0.5 text-[11px] font-medium text-ink-2 tnum">{count}</span>
      ) : null}
    </RadixTabs.Trigger>
  );
}
