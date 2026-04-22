import { useEffect } from "react";
import clsx from "clsx";
import { Sidebar } from "./Sidebar";
import { MainPanel } from "./MainPanel";
import { OutputPane } from "./OutputPane";
import { useUIStore } from "@/state/ui";
import { usePlatform } from "@/lib/platform";
import {
  getOutputPaneCollapsed,
  listRecentRepos,
  setOutputPaneCollapsed as persistOutputPaneCollapsed,
} from "@/lib/commands";
import { detectCli } from "@/lib/settings";

export function Shell() {
  const platform = usePlatform();
  const outputPaneCollapsed = useUIStore((s) => s.outputPaneCollapsed);
  const setOutputPaneCollapsed = useUIStore((s) => s.setOutputPaneCollapsed);
  const setRecentRepos = useUIStore((s) => s.setRecentRepos);
  const activeRepo = useUIStore((s) => s.activeRepo);
  const setActiveSection = useUIStore((s) => s.setActiveSection);

  // Hydrate persisted UI state + recent repos on mount.
  useEffect(() => {
    void getOutputPaneCollapsed().then(setOutputPaneCollapsed);
    void listRecentRepos().then(setRecentRepos);
    // Task 6.6: if the CLI isn't found, jump to Settings so the user sees
    // the "CLI not found" callout immediately.
    void detectCli().then((status) => {
      if (!status.found) setActiveSection("settings");
    });
  }, [setOutputPaneCollapsed, setRecentRepos, setActiveSection]);

  const isMac = platform === "macos";

  return (
    <div
      className={clsx(
        "pg-shell flex h-screen w-screen overflow-hidden",
        // On macOS we let NSVisualEffectView vibrancy show through.
        // On Linux/other we provide an opaque muted background that matches
        // the frosted look as closely as possible without compositor support.
        isMac
          ? "bg-transparent"
          : "bg-stone-50/95 backdrop-blur-md",
      )}
    >
      <Sidebar isMac={isMac} />
      <div className="flex flex-1 flex-col min-w-0">
        {/* Header / title bar drag region (covers the macOS traffic-light area). */}
        <header
          data-tauri-drag-region
          className={clsx(
            "flex items-center justify-between gap-3 px-6",
            "h-11 shrink-0 border-b border-ink-200/60",
            isMac ? "bg-white/40 backdrop-blur" : "bg-white/80",
          )}
        >
          <div className="flex items-center gap-2 text-[12px] text-ink-500">
            <span className="font-medium text-ink-700">playwright-god</span>
            {activeRepo && (
              <>
                <span className="text-ink-300">·</span>
                <span className="font-mono text-[11px] truncate max-w-[60vw]">
                  {activeRepo}
                </span>
              </>
            )}
          </div>
          <StatusBarTrailing />
        </header>

        <main className="flex flex-1 min-h-0">
          <MainPanel />
        </main>

        {!outputPaneCollapsed && <OutputPane />}
        <StatusBar />
      </div>
    </div>
  );
}

function StatusBarTrailing() {
  return null;
}

function StatusBar() {
  const collapsed = useUIStore((s) => s.outputPaneCollapsed);
  const toggle = useUIStore((s) => s.toggleOutputPane);
  const handleToggle = () => {
    toggle();
    // Persist after the store has flipped (read the new value via getState).
    void persistOutputPaneCollapsed(!collapsed);
  };
  return (
    <footer
      className="flex h-7 shrink-0 items-center justify-between gap-3
                 border-t border-ink-200/60 bg-white/70 px-4 text-[11px] text-ink-500"
    >
      <span>Idle</span>
      <button
        type="button"
        onClick={handleToggle}
        className="rounded px-2 py-0.5 text-ink-600 hover:bg-ink-100"
      >
        {collapsed ? "Show output" : "Hide output"}
      </button>
    </footer>
  );
}
