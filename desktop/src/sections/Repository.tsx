import { Panel } from "@/components/Panel";
import { useUIStore } from "@/state/ui";
import {
  addRecentRepo,
  pickRepository,
} from "@/lib/commands";

export function Repository() {
  const activeRepo = useUIStore((s) => s.activeRepo);
  const setActiveRepo = useUIStore((s) => s.setActiveRepo);
  const recent = useUIStore((s) => s.recentRepos);
  const setRecentRepos = useUIStore((s) => s.setRecentRepos);

  const open = async () => {
    const path = await pickRepository();
    if (!path) return;
    setActiveRepo(path);
    const updated = await addRecentRepo(path);
    if (updated.length) setRecentRepos(updated);
  };

  return (
    <div className="flex flex-col gap-6">
      <Panel>
        <div className="flex items-start justify-between gap-6">
          <div className="flex flex-col gap-1">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-500">
              Active Repository
            </div>
            {activeRepo ? (
              <div className="font-mono text-[13px] text-ink-800 break-all">
                {activeRepo}
              </div>
            ) : (
              <div className="text-[13px] text-ink-500">
                No repository selected.
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={open}
            className="rounded-lg bg-accent px-4 py-2 text-[13px] font-medium text-white shadow-soft transition-colors hover:bg-accent-hover"
          >
            Open Repository…
          </button>
        </div>
      </Panel>

      <Panel>
        <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-ink-500">
          Recent Repositories
        </div>
        {recent.length === 0 ? (
          <div className="text-[13px] text-ink-500">
            Recent repositories will appear here once you open one.
          </div>
        ) : (
          <ul className="flex flex-col">
            {recent.map((r) => (
              <li key={r.path}>
                <button
                  type="button"
                  onClick={() => setActiveRepo(r.path)}
                  className="flex w-full items-center justify-between gap-4 rounded-lg px-3 py-2 text-left text-[13px] hover:bg-ink-100"
                >
                  <span className="font-mono truncate text-ink-800">
                    {r.path}
                  </span>
                  <span className="shrink-0 text-[11px] text-ink-400">
                    {new Date(r.openedAt).toLocaleString()}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
