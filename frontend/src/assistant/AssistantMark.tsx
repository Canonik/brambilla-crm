import { cn } from "@/lib/cn";

/**
 * The assistant's mark: gentian disc with the one signal-orange dot, the
 * registration mark printed on Brambilla's labels. `working` makes the dot
 * breathe while a request is in flight.
 */
export function AssistantMark({ className, size = 20, working = false }: { className?: string; size?: number; working?: boolean }) {
  return (
    <span
      aria-hidden
      className={cn("inline-flex shrink-0 items-center justify-center rounded-full bg-gentian text-white", className)}
      style={{ width: size, height: size }}
    >
      <span className={cn("block rounded-full bg-signal", working && "mark-working")} style={{ width: size * 0.38, height: size * 0.38 }} />
    </span>
  );
}
