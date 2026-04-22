import clsx from "clsx";
import type { ReactNode } from "react";

interface PanelProps {
  children: ReactNode;
  className?: string;
}

/** Card / panel surface with the soft shadow + frosted background. */
export function Panel({ children, className }: PanelProps) {
  return (
    <div
      className={clsx(
        "rounded-2xl border border-ink-200/60 bg-white/80 backdrop-blur p-6 shadow-soft",
        className,
      )}
    >
      {children}
    </div>
  );
}
