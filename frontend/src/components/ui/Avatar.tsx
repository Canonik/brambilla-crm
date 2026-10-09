import { cn } from "@/lib/cn";
import { initials } from "@/lib/format";

const hues = ["bg-[#dbe7f3] text-[#1f4b7a]", "bg-[#e3ecdf] text-[#2f5a2a]", "bg-[#f1e4d6] text-[#7a4a1f]", "bg-[#e8e0f0] text-[#4f3570]", "bg-[#e6e8ec] text-[#3b4552]"];

function hueFor(text: string) {
  let h = 0;
  for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) >>> 0;
  return hues[h % hues.length]!;
}

export function Avatar({
  name,
  size = "md",
  square,
  className,
}: {
  name: string | null | undefined;
  size?: "xs" | "sm" | "md" | "lg";
  square?: boolean;
  className?: string;
}) {
  const label = name ?? "";
  const sizes = {
    xs: "size-5 text-[9px]",
    sm: "size-6 text-[10px]",
    md: "size-8 text-[12px]",
    lg: "size-11 text-[15px]",
  };
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex shrink-0 select-none items-center justify-center font-semibold",
        square ? "rounded-md" : "rounded-full",
        sizes[size],
        hueFor(label),
        className,
      )}
    >
      {initials(label)}
    </span>
  );
}
