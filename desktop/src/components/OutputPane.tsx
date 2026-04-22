import { useEffect, useRef } from "react";
import { Virtuoso, type VirtuosoHandle } from "react-virtuoso";
import AnsiToHtml from "ansi-to-html";
import { useOutputStore } from "@/state/output";
import { exportRows } from "@/lib/csv";

const ANSI = new AnsiToHtml({
  fg: "#1c1917",
  bg: "transparent",
  newline: false,
  escapeXML: true,
});

export function OutputPane() {
  const lines = useOutputStore((s) => s.lines);
  const clear = useOutputStore((s) => s.clear);
  const ref = useRef<VirtuosoHandle | null>(null);

  // Auto-scroll to the bottom when new lines arrive.
  useEffect(() => {
    if (lines.length === 0) return;
    ref.current?.scrollToIndex({ index: lines.length - 1, behavior: "auto" });
  }, [lines.length]);

  return (
    <section
      className="flex h-outputPane shrink-0 flex-col border-t border-ink-200/60 bg-white/80"
      aria-label="Run output"
    >
      <header className="flex h-8 shrink-0 items-center justify-between gap-3 border-b border-ink-200/60 px-4">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-500">
          Output
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() =>
              exportRows(
                lines,
                [
                  { header: "timestamp", value: (l) => l.ts },
                  { header: "stream", value: (l) => l.stream },
                  { header: "line", value: (l) => l.text },
                ],
                "output.csv",
              )
            }
            disabled={lines.length === 0}
            className="rounded px-2 py-0.5 text-[11px] text-ink-600 hover:bg-ink-100 disabled:opacity-40"
          >
            Export
          </button>
          <button
            type="button"
            onClick={clear}
            className="rounded px-2 py-0.5 text-[11px] text-ink-600 hover:bg-ink-100"
          >
            Clear
          </button>
        </div>
      </header>
      <div className="pg-selectable flex-1 min-h-0 overflow-hidden font-mono text-[12px] leading-[18px]">
        <Virtuoso
          ref={ref}
          data={lines}
          itemContent={(_, line) => (
            <div className="px-4">
              <span
                className="whitespace-pre-wrap break-words text-ink-800"
                dangerouslySetInnerHTML={{ __html: ANSI.toHtml(line.text) }}
              />
            </div>
          )}
          followOutput
        />
      </div>
    </section>
  );
}
