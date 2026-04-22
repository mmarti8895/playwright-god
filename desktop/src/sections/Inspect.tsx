import { useEffect, useState } from "react";
import * as Collapsible from "@radix-ui/react-collapsible";
import clsx from "clsx";
import { Panel } from "@/components/Panel";
import { useUIStore } from "@/state/ui";
import {
  discoverRepo,
  inspectRepo,
  previewPrompt,
  type PromptPreview,
} from "@/lib/runs";

export function Inspect() {
  const repo = useUIStore((s) => s.activeRepo);
  const version = useUIStore((s) => s.artifactsVersion);
  const [inspectData, setInspectData] = useState<unknown>(null);
  const [discoverData, setDiscoverData] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [description, setDescription] = useState("");
  const [preview, setPreview] = useState<PromptPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  useEffect(() => {
    if (!repo) {
      setInspectData(null);
      setDiscoverData(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.allSettled([inspectRepo(repo), discoverRepo(repo)]).then(
      ([insp, disc]) => {
        if (cancelled) return;
        if (insp.status === "fulfilled") setInspectData(insp.value);
        else setError(String(insp.reason));
        if (disc.status === "fulfilled") setDiscoverData(disc.value);
        else if (insp.status !== "rejected")
          setError(String(disc.reason));
        setLoading(false);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [repo, version]);

  const onPreview = async () => {
    if (!repo || !description.trim() || previewLoading) return;
    setPreviewLoading(true);
    setPreviewError(null);
    setPreview(null);
    try {
      const r = await previewPrompt(repo, description.trim());
      setPreview(r);
    } catch (e) {
      setPreviewError(String(e));
    } finally {
      setPreviewLoading(false);
    }
  };

  if (!repo) {
    return (
      <Panel className="flex h-full items-center justify-center">
        <div className="text-[13px] text-ink-500">
          Open a repository to inspect it.
        </div>
      </Panel>
    );
  }

  const routes = pickArray(discoverData, ["routes"]);
  const journeys = pickArray(discoverData, ["journeys"]);
  const candidates = pickArray(discoverData, [
    "scenario_candidates",
    "candidates",
    "scenarios",
  ]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto">
      <Panel className="flex flex-col gap-3">
        <h2 className="text-[14px] font-semibold text-ink-900">
          Repository classification
        </h2>
        {loading && (
          <div className="text-[12px] text-ink-500">Running inspect…</div>
        )}
        {error && (
          <div className="rounded-md border border-rose-300 bg-rose-50 px-3 py-2 text-[12px] text-rose-900">
            {error}
          </div>
        )}
        {inspectData != null && (
          <pre className="max-h-72 overflow-auto rounded bg-ink-50 p-3 font-mono text-[11px] text-ink-800">
            {JSON.stringify(inspectData, null, 2)}
          </pre>
        )}
      </Panel>

      <Panel className="flex flex-col gap-3">
        <h2 className="text-[14px] font-semibold text-ink-900">Discover</h2>
        <Section title={`Routes (${routes.length})`} defaultOpen>
          <JsonList items={routes} keyOf={(r) => labelFor(r, ["path", "id", "url"])} />
        </Section>
        <Section title={`Journeys (${journeys.length})`}>
          <JsonList items={journeys} keyOf={(r) => labelFor(r, ["id", "name", "title"])} />
        </Section>
        <Section title={`Scenario candidates (${candidates.length})`}>
          <JsonList
            items={candidates}
            keyOf={(r) => labelFor(r, ["title", "name", "id", "description"])}
          />
        </Section>
      </Panel>

      <Panel className="flex flex-col gap-3">
        <h2 className="text-[14px] font-semibold text-ink-900">
          Prompt preview
        </h2>
        <p className="text-[12px] text-ink-500">
          Runs <code>generate --dry-run --print-prompt</code> against your CLI to
          show the assembled prompt without performing any LLM call.
        </p>
        <div className="flex flex-col gap-2">
          <textarea
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe the test you want to generate, e.g. “user logs in with valid credentials”"
            className="rounded-md border border-ink-200 bg-white px-3 py-2 text-[13px] focus:border-ink-400 focus:outline-none"
          />
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onPreview}
              disabled={previewLoading || !description.trim()}
              className="rounded-md bg-ink-900 px-4 py-2 text-[12px] font-medium text-white hover:bg-ink-800 disabled:opacity-40"
            >
              {previewLoading ? "Building…" : "Preview prompt"}
            </button>
            {previewError && (
              <span className="text-[11px] text-rose-700">{previewError}</span>
            )}
          </div>
        </div>
        {preview && (
          <pre className="max-h-[480px] overflow-auto rounded bg-ink-50 p-3 font-mono text-[11px] text-ink-800">
            {preview.prompt || "(empty prompt)"}
          </pre>
        )}
      </Panel>
    </div>
  );
}

function Section({
  title,
  children,
  defaultOpen = false,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Collapsible.Root open={open} onOpenChange={setOpen}>
      <Collapsible.Trigger asChild>
        <button
          type="button"
          className="flex w-full items-center justify-between rounded-md border border-ink-200/60 bg-ink-50 px-3 py-2 text-left text-[12px] font-medium text-ink-800 hover:bg-ink-100"
        >
          <span>{title}</span>
          <span className="text-ink-400">{open ? "▾" : "▸"}</span>
        </button>
      </Collapsible.Trigger>
      <Collapsible.Content className="mt-2">{children}</Collapsible.Content>
    </Collapsible.Root>
  );
}

function JsonList({
  items,
  keyOf,
}: {
  items: unknown[];
  keyOf: (item: unknown) => string;
}) {
  if (items.length === 0) {
    return (
      <div className="px-3 py-2 text-[12px] text-ink-400">No entries.</div>
    );
  }
  return (
    <ul className="flex flex-col gap-1">
      {items.map((it, i) => (
        <JsonItem key={i} label={keyOf(it)} value={it} />
      ))}
    </ul>
  );
}

function JsonItem({ label, value }: { label: string; value: unknown }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="rounded border border-ink-100">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={clsx(
          "flex w-full items-center justify-between px-3 py-1.5 text-left text-[12px] text-ink-800 hover:bg-ink-50",
        )}
      >
        <span className="truncate">{label}</span>
        <span className="text-ink-400">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <pre className="max-h-60 overflow-auto bg-ink-50 px-3 py-2 font-mono text-[10px] text-ink-700">
          {JSON.stringify(value, null, 2)}
        </pre>
      )}
    </li>
  );
}

function pickArray(data: unknown, keys: string[]): unknown[] {
  if (!data || typeof data !== "object") return [];
  const obj = data as Record<string, unknown>;
  for (const k of keys) {
    const v = obj[k];
    if (Array.isArray(v)) return v;
  }
  return [];
}

function labelFor(item: unknown, keys: string[]): string {
  if (item == null) return "(null)";
  if (typeof item === "string") return item;
  if (typeof item !== "object") return String(item);
  const obj = item as Record<string, unknown>;
  // Prefer `method + path` for routes.
  if (typeof obj.method === "string" && typeof obj.path === "string") {
    return `${obj.method} ${obj.path}`;
  }
  for (const k of keys) {
    const v = obj[k];
    if (typeof v === "string" && v.trim()) return v;
  }
  return JSON.stringify(item).slice(0, 80);
}
