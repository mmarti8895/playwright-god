import clsx from "clsx";
import { useUIStore, type SectionId } from "@/state/ui";

interface Item {
  id: SectionId;
  label: string;
  group?: string;
}

const ITEMS: Item[] = [
  { id: "repository", label: "Repository", group: "Workspace" },
  { id: "memory-map", label: "Memory Map", group: "Artifacts" },
  { id: "flow-graph", label: "Flow Graph", group: "Artifacts" },
  { id: "coverage", label: "Coverage & Gaps", group: "Artifacts" },
  { id: "rag", label: "RAG Search", group: "Artifacts" },
  { id: "generation", label: "Generation", group: "Run" },
  { id: "codegen-stream", label: "Codegen Stream", group: "Run" },
  { id: "inspect", label: "Dry Run / Inspect", group: "Run" },
  { id: "audit-log", label: "Audit Log", group: "Run" },
  { id: "settings", label: "Settings", group: "App" },
];

interface SidebarProps {
  isMac: boolean;
}

export function Sidebar({ isMac }: SidebarProps) {
  const active = useUIStore((s) => s.activeSection);
  const setActive = useUIStore((s) => s.setActiveSection);

  // Group consecutive items with the same group into sections.
  const grouped: { group: string; items: Item[] }[] = [];
  for (const item of ITEMS) {
    const g = item.group ?? "";
    const last = grouped[grouped.length - 1];
    if (last && last.group === g) last.items.push(item);
    else grouped.push({ group: g, items: [item] });
  }

  return (
    <aside
      data-tauri-drag-region
      className={clsx(
        "pg-sidebar flex w-sidebar shrink-0 flex-col gap-4",
        "border-r border-ink-200/60 px-3 pt-12 pb-3",
        // The space-12 on top reserves room for the macOS traffic-light overlay
        // when titleBarStyle is Overlay.
        isMac
          ? "bg-transparent"
          : "bg-stone-100/90 backdrop-blur-md",
      )}
    >
      <div className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-ink-400">
        Playwright God
      </div>

      <nav aria-label="Primary" className="flex flex-col gap-4 overflow-y-auto pr-1">
        {grouped.map((section) => (
          <div key={section.group} className="flex flex-col gap-0.5">
            {section.group && (
              <div className="px-3 pb-1 text-[10px] font-medium uppercase tracking-wider text-ink-400">
                {section.group}
              </div>
            )}
            {section.items.map((item) => {
              const selected = item.id === active;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setActive(item.id)}
                  className={clsx(
                    "flex items-center gap-2 rounded-lg px-3 py-1.5 text-left text-[13px] transition-colors",
                    "outline-none focus-visible:ring-2 focus-visible:ring-accent",
                    selected
                      ? isMac
                        ? "bg-white/70 text-ink-900 shadow-soft"
                        : "bg-stone-200 text-ink-900"
                      : "text-ink-600 hover:bg-white/40",
                  )}
                  aria-current={selected ? "page" : undefined}
                >
                  <span className="flex-1 truncate">{item.label}</span>
                </button>
              );
            })}
          </div>
        ))}
      </nav>
    </aside>
  );
}
