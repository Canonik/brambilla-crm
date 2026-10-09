import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";
import type { Tone } from "@/lib/stages";

const tones: Record<Tone, string> = {
  brand: "bg-gentian-soft text-gentian border-gentian-line",
  signal: "bg-signal-soft text-signal-deep border-[#f5c3a6]",
  good: "bg-good-soft text-good border-[#bfdcc0]",
  warn: "bg-warn-soft text-warn border-[#efd9a6]",
  bad: "bg-bad-soft text-bad border-[#f1c0bb]",
  muted: "bg-surface-3 text-ink-2 border-line",
  neutral: "bg-surface text-ink border-line-strong",
  none: "bg-transparent text-ink-3 border-dashed border-line-strong",
};

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
  dot?: boolean;
  icon?: ReactNode;
  size?: "sm" | "md";
}

export function Badge({ tone = "neutral", dot, icon, size = "md", className, children, ...rest }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-sm border font-medium leading-none",
        size === "sm" ? "h-5 px-1.5 text-[11.5px]" : "h-6 px-2 text-[12px]",
        tones[tone],
        className,
      )}
      {...rest}
    >
      {dot ? <span className="size-1.5 rounded-full bg-current" aria-hidden /> : icon}
      {children}
    </span>
  );
}
