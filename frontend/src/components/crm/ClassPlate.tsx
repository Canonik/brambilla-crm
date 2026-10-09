import { cn } from "@/lib/cn";
import { classTone } from "@/lib/stages";

/**
 * The customer class (A, B, C) as a stamped plate, the way a class label would
 * sit on a rack in Brambilla's warehouse. Class A is the one place the UI
 * uses the RAL 2004 orange at full strength.
 */
export function ClassPlate({
  value,
  size = "md",
  className,
  title,
}: {
  value: string | null | undefined;
  size?: "sm" | "md" | "lg";
  className?: string;
  title?: string;
}) {
  const tone = classTone(value);
  const letter = (value ?? "").trim().toUpperCase() || "–";
  const sizes = {
    sm: "size-6 text-[12px] rounded-sm",
    md: "size-8 text-[15px] rounded-md",
    lg: "size-14 text-[30px] rounded-lg",
  };
  const tones = {
    signal: "bg-signal text-white",
    brand: "bg-gentian text-white",
    neutral: "bg-surface-3 text-ink border border-line-strong",
    none: "bg-transparent text-ink-3 border border-dashed border-line-strong",
  } as const;
  const key = tone === "signal" || tone === "brand" || tone === "neutral" ? tone : "none";
  return (
    <span
      title={title ?? (letter === "–" ? "No class: no revenue in 2025" : `Class ${letter}`)}
      aria-label={letter === "–" ? "No class" : `Class ${letter}`}
      className={cn(
        "inline-flex shrink-0 select-none items-center justify-center font-bold font-wide leading-none tracking-tight",
        sizes[size],
        tones[key],
        className,
      )}
    >
      {letter}
    </span>
  );
}
