import { useState } from "react";
import { Panel } from "@/components/Panel";
import { useUIStore } from "@/state/ui";
import { ragSearch, type SearchHit } from "@/lib/artifacts";

export function RagView() {
  const repo = useUIStore((s) => s.activeRepo);
  const setActiveSection = useUIStore((s) => s.setActiveSection);
  const [query, setQuery] = useState("");
  const [topN, setTopN] = useState(10);
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  if (!repo) {
    return (
      <Panel className="flex h-full items-center justify-center">
        <div className="text-[13px] text-ink-500">
          Open a repository to search its index.
        </div>
      </Panel>
    );
  }

  const onSearch = async () => {
    if (!query.trim() || loading) return;
    setLoading(true);
    setError(null);
    setSearched(true);
    const result = await ragSearch(repo, query.trim(), topN);
    setHits(result.hits);
    setError(result.error);
    setLoading(false);
  };

  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") void onSearch();
  };

  return (
    <Panel className="flex h-full min-h-0 flex-col gap-3 overflow-hidden">
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKey}
          placeholder='Search the repository index ("user login flow", "auth middleware", …)'
          className="flex-1 rounded-md border border-ink-200 bg-white px-3 py-2 text-[13px] focus:border-ink-400 focus:outline-none"
        />
        <input
          type="number"
          min={1}
          max={50}
          value={topN}
          onChange={(e) => setTopN(Math.max(1, Math.min(50, Number(e.target.value) || 10)))}
          className="w-20 rounded-md border border-ink-200 bg-white px-2 py-2 text-[12px] focus:border-ink-400 focus:outline-none"
          title="Top-N results"
        />
        <button
          type="button"
          onClick={onSearch}
          disabled={loading || !query.trim()}
          className="rounded-md bg-ink-900 px-4 py-2 text-[12px] font-medium text-white hover:bg-ink-800 disabled:opacity-40"
        >
          {loading ? "Searching…" : "Search"}
        </button>
      </div>

      {error && (
        <div className="rounded-md border border-rose-300 bg-rose-50 px-3 py-2 text-[12px] text-rose-900">
          <div className="font-medium">Search failed</div>
          <div className="mt-1 whitespace-pre-wrap font-mono text-[11px]">{error}</div>
          <div className="mt-2 text-[11px]">
            If the repository hasn't been indexed yet, run the{" "}
            <button
              type="button"
              onClick={() => setActiveSection("generation")}
              className="underline hover:text-rose-700"
            >
              index step
            </button>{" "}
            from the Generation tab.
          </div>
        </div>
      )}

      <div className="flex-1 min-h-0 overflow-y-auto">
        {!searched && !loading && (
          <div className="flex h-full items-center justify-center text-[13px] text-ink-400">
            Enter a query above to search the repository index.
          </div>
        )}
        {searched && !loading && !error && hits.length === 0 && (
          <div className="flex h-full items-center justify-center text-[13px] text-ink-500">
            No results.
          </div>
        )}
        <ul className="flex flex-col gap-2">
          {hits.map((h, i) => (
            <li
              key={`${h.file}-${h.line}-${i}`}
              className="rounded-xl border border-ink-200/60 bg-white p-3"
            >
              <header className="mb-1 flex items-baseline justify-between gap-3">
                <span className="font-mono text-[12px] text-ink-800 truncate">
                  {h.file}
                  {h.line != null ? `:${h.line}` : ""}
                </span>
                <span className="shrink-0 rounded bg-ink-100 px-2 py-0.5 font-mono text-[10px] text-ink-700">
                  {h.score.toFixed(3)}
                </span>
              </header>
              {h.content && (
                <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded-md bg-ink-50 px-3 py-2 font-mono text-[11px] leading-snug text-ink-800">
                  {h.content}
                </pre>
              )}
            </li>
          ))}
        </ul>
      </div>
    </Panel>
  );
}
