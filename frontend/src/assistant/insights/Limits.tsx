import { Eye, Lightbulb } from "lucide-react";
import { cn } from "@/lib/cn";
import type { InsightLimitation } from "../evidence";

const TONE: Record<InsightLimitation["tone"], string> = {
  warn: "border-l-warn",
  bad: "border-l-bad",
  muted: "border-l-line-strong",
  brand: "border-l-gentian",
};

/** Each limit says whether it was observed in the trace or is a reading of it. */
export function Limits({ items }: { items: InsightLimitation[] }) {
  const observed = items.filter((item) => item.basis === "observed");
  const interpretations = items.filter((item) => item.basis === "interpretation");
  return (
    <div className="space-y-4">
      <section aria-labelledby="insight-limits-observed">
        <h4 id="insight-limits-observed" className="flex items-center gap-1.5 text-[11.5px] font-semibold text-ink">
          <Eye className="size-3.5 text-gentian" aria-hidden /> Observed in the trace
        </h4>
        {observed.length ? (
          <ul className="mt-1.5 space-y-1.5">
            {observed.map((item, index) => (
              <li key={index} className={cn("border-l-2 pl-2.5 text-[11.5px] leading-relaxed text-ink-2", TONE[item.tone])}>
                {item.step ? <span className="tnum mr-1 text-ink-3">step {item.step}:</span> : null}{item.text}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1.5 text-[11.5px] text-ink-2">Every observed operation settled with a confirmed outcome.</p>
        )}
      </section>
      <section aria-labelledby="insight-limits-reading">
        <h4 id="insight-limits-reading" className="flex items-center gap-1.5 text-[11.5px] font-semibold text-ink">
          <Lightbulb className="size-3.5 text-warn" aria-hidden /> Interpretation, not observation
        </h4>
        <ul className="mt-1.5 space-y-1.5">
          {interpretations.map((item, index) => (
            <li key={index} className={cn("border-l-2 border-dashed pl-2.5 text-[11.5px] leading-relaxed text-ink-2", TONE[item.tone])}>
              {item.step ? <span className="tnum mr-1 text-ink-3">step {item.step}:</span> : null}{item.text}
            </li>
          ))}
          <li className="border-l-2 border-dashed border-l-line-strong pl-2.5 text-[11.5px] leading-relaxed text-ink-2">
            This panel shows what the backend observed while handling the reply. It has no access to the model's hidden reasoning, prompts, activations or confidence, and it does not claim any.
          </li>
        </ul>
      </section>
    </div>
  );
}
