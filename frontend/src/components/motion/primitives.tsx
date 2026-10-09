import { useEffect, useRef, useState, type ReactNode } from "react";
import { MotionConfig, animate, motion, useReducedMotion } from "motion/react";
import { useLocation } from "react-router-dom";

// The few motion patterns the CRM uses, in one place so they stay consistent:
// one ease, short durations, every entrance answering a navigation or an
// action. `MotionConfig reducedMotion="user"` turns transforms off for people
// who asked their OS for less motion; opacity fades still run.

export const EASE_OUT = [0.22, 1, 0.36, 1] as const;
export const SPRING = { type: "spring", stiffness: 420, damping: 34, mass: 0.8 } as const;

export function MotionProvider({ children }: { children: ReactNode }) {
  return <MotionConfig reducedMotion="user">{children}</MotionConfig>;
}

/** Fade and rise in on mount. `delay` in seconds. */
export function Rise({
  children,
  delay = 0,
  className,
  y = 8,
  duration = 0.32,
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
  y?: number;
  duration?: number;
}) {
  return (
    <motion.div className={className} initial={{ opacity: 0, y }} animate={{ opacity: 1, y: 0 }} transition={{ duration, delay, ease: EASE_OUT }}>
      {children}
    </motion.div>
  );
}

/** Variants for a list whose items appear one after the other. */
export const staggerParent = {
  hidden: {},
  show: { transition: { staggerChildren: 0.045, delayChildren: 0.04 } },
};
export const staggerChild = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { duration: 0.3, ease: EASE_OUT } },
};

/** Remounts and fades the page content when the route changes. */
export function PageTransition({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  return (
    <motion.div
      key={pathname}
      className="flex min-h-0 flex-1 flex-col"
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0, transition: { duration: 0.2, ease: EASE_OUT } }}
    >
      {children}
    </motion.div>
  );
}

/** A number that counts up to its value; the final text is always exact. */
export function CountUp({
  value,
  format = (n: number) => String(Math.round(n)),
  duration = 0.9,
  className,
}: {
  value: number;
  format?: (n: number) => string;
  duration?: number;
  className?: string;
}) {
  const reduced = useReducedMotion();
  const [display, setDisplay] = useState(() => format(reduced ? value : 0));
  const from = useRef(0);
  const formatRef = useRef(format);
  formatRef.current = format;

  useEffect(() => {
    if (reduced) {
      from.current = value;
      setDisplay(formatRef.current(value));
      return;
    }
    const controls = animate(from.current, value, {
      duration,
      ease: EASE_OUT,
      onUpdate: (v) => setDisplay(formatRef.current(v)),
      onComplete: () => setDisplay(formatRef.current(value)),
    });
    from.current = value;
    return () => controls.stop();
  }, [value, duration, reduced]);

  return <span className={className}>{display}</span>;
}

/** A horizontal bar that grows to its percentage. */
export function GrowBar({ percent, className, delay = 0 }: { percent: number; className?: string; delay?: number }) {
  const width = `${Math.max(0, Math.min(100, percent))}%`;
  return <motion.div className={className} initial={{ width: 0 }} animate={{ width }} transition={{ duration: 0.6, delay, ease: EASE_OUT }} />;
}
