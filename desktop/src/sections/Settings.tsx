// Settings section: provider/model/Ollama URL/CLI-timeout/CLI-path form,
// API-key masked input persisted to the OS keyring, reset-to-defaults
// confirmation, and a "CLI not found" callout (task 6.6).

import { useEffect, useMemo, useState } from "react";
import * as AlertDialog from "@radix-ui/react-alert-dialog";
import * as Select from "@radix-ui/react-select";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import clsx from "clsx";

import { Panel } from "@/components/Panel";
import {
  apiKeyEnvVar,
  DEFAULT_SETTINGS,
  PROVIDERS,
  type CliStatus,
  type Provider,
  type SecretsHealth,
  type Settings as SettingsT,
  detectCli,
  deleteSecret,
  getSecret,
  getSettings,
  resetSettings,
  saveSettings,
  secretsHealth,
  setSecret,
  validateSettings,
} from "@/lib/settings";

const inTauri = (): boolean =>
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

export function Settings() {
  const [settings, setSettings] = useState<SettingsT>(DEFAULT_SETTINGS);
  const [apiKey, setApiKey] = useState<string>("");
  const [apiKeyDirty, setApiKeyDirty] = useState(false);
  const [revealKey, setRevealKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cli, setCli] = useState<CliStatus | null>(null);
  const [secrets, setSecrets] = useState<SecretsHealth | null>(null);

  // Load existing settings + status on mount.
  useEffect(() => {
    void (async () => {
      const s = await getSettings();
      setSettings(s);
      setCli(await detectCli());
      setSecrets(await secretsHealth());
      const env = apiKeyEnvVar(s.provider);
      if (env) {
        const v = await getSecret(env);
        setApiKey(v ?? "");
      }
    })();
  }, []);

  // When the provider changes, refresh the masked key for the new provider.
  useEffect(() => {
    void (async () => {
      const env = apiKeyEnvVar(settings.provider);
      if (!env) {
        setApiKey("");
        setApiKeyDirty(false);
        return;
      }
      const v = await getSecret(env);
      setApiKey(v ?? "");
      setApiKeyDirty(false);
    })();
  }, [settings.provider]);

  const validationError = useMemo(() => validateSettings(settings), [settings]);
  const canSave = !saving && validationError === null;
  const showSaved =
    savedAt !== null && Date.now() - savedAt < 4000;

  const handleField = <K extends keyof SettingsT>(key: K, value: SettingsT[K]) => {
    setSettings((s) => ({ ...s, [key]: value }));
    setSavedAt(null);
  };

  const handleBrowseCli = async () => {
    if (!inTauri()) return;
    try {
      const picked = await openDialog({
        multiple: false,
        directory: false,
        title: "Select playwright-god executable",
      });
      if (typeof picked === "string") {
        handleField("cli_path", picked);
      }
    } catch {
      /* user cancelled */
    }
  };

  const handleSave = async () => {
    if (!canSave) return;
    setSaving(true);
    setError(null);
    try {
      const validated = await saveSettings(settings);
      setSettings(validated);
      const env = apiKeyEnvVar(validated.provider);
      if (env && apiKeyDirty) {
        if (apiKey.trim()) {
          await setSecret(env, apiKey.trim());
        } else {
          await deleteSecret(env);
        }
        setApiKeyDirty(false);
      }
      setCli(await detectCli());
      setSecrets(await secretsHealth());
      setSavedAt(Date.now());
    } catch (e) {
      setError((e as Error).message ?? String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    setSaving(true);
    try {
      const fresh = await resetSettings();
      setSettings(fresh);
      setApiKey("");
      setApiKeyDirty(false);
      setCli(await detectCli());
      setSecrets(await secretsHealth());
      setSavedAt(Date.now());
    } finally {
      setSaving(false);
    }
  };

  const apiKeyEnv = apiKeyEnvVar(settings.provider);

  return (
    <div className="flex flex-col gap-4">
      {cli && !cli.found && (
        <div
          role="alert"
          className="rounded-md border border-rose-200 bg-rose-50/80 px-3 py-2 text-[12px] text-rose-800"
        >
          <strong className="font-semibold">playwright-god CLI not found.</strong>{" "}
          Install it (<code>pip install -e .</code>) so it's on <code>PATH</code>,
          or set the <em>CLI path</em> field below.
        </div>
      )}
      {secrets && !secrets.keyring_ok && (
        <div className="rounded-md border border-amber-200 bg-amber-50/80 px-3 py-2 text-[12px] text-amber-800">
          The OS keyring was unavailable; API keys are saved to a local
          plaintext file (mode 0600) at{" "}
          <code>{secrets.fallback_path ?? "<app-config>/secrets.json"}</code>.
        </div>
      )}

      <Panel>
        <form
          className="flex flex-col gap-4 p-5"
          onSubmit={(e) => {
            e.preventDefault();
            void handleSave();
          }}
        >
          <h2 className="text-[15px] font-semibold text-ink-900">LLM provider</h2>

          <Field label="Provider">
            <ProviderSelect
              value={settings.provider}
              onChange={(p) => handleField("provider", p)}
            />
          </Field>

          <Field
            label="Model"
            hint="Leave blank to use the provider's default."
          >
            <input
              className={inputCls}
              value={settings.model}
              onChange={(e) => handleField("model", e.target.value)}
              placeholder="gpt-4o"
            />
          </Field>

          {apiKeyEnv && (
            <Field label={`API key (${apiKeyEnv})`}>
              <div className="flex items-center gap-2">
                <input
                  type={revealKey ? "text" : "password"}
                  className={inputCls}
                  value={apiKey}
                  onChange={(e) => {
                    setApiKey(e.target.value);
                    setApiKeyDirty(true);
                    setSavedAt(null);
                  }}
                  placeholder={revealKey ? "" : "••••••••••••"}
                  autoComplete="off"
                  spellCheck={false}
                />
                <button
                  type="button"
                  onClick={() => setRevealKey((v) => !v)}
                  className="rounded-md px-2 py-1 text-[11px] text-ink-600 ring-1 ring-ink-200 hover:bg-ink-50"
                >
                  {revealKey ? "Hide" : "Show"}
                </button>
              </div>
            </Field>
          )}

          {settings.provider === "ollama" && (
            <Field label="Ollama URL">
              <input
                className={inputCls}
                value={settings.ollama_url}
                onChange={(e) => handleField("ollama_url", e.target.value)}
                placeholder="http://localhost:11434"
              />
            </Field>
          )}

          {settings.provider === "playwright-cli" && (
            <Field
              label="Playwright CLI timeout (seconds)"
              hint="How long to wait for the Inspector window to close."
            >
              <input
                type="number"
                min={1}
                step={1}
                className={inputCls}
                value={settings.playwright_cli_timeout}
                onChange={(e) =>
                  handleField(
                    "playwright_cli_timeout",
                    Math.max(1, Number.parseInt(e.target.value, 10) || 1),
                  )
                }
              />
            </Field>
          )}

          <h2 className="mt-2 text-[15px] font-semibold text-ink-900">
            playwright-god CLI
          </h2>

          <Field
            label="CLI path"
            hint={
              cli?.found
                ? `Detected: ${cli.path} (from ${cli.source})`
                : "Leave blank to use the binary on $PATH."
            }
          >
            <div className="flex items-center gap-2">
              <input
                className={inputCls}
                value={settings.cli_path ?? ""}
                onChange={(e) => handleField("cli_path", e.target.value || null)}
                placeholder="/usr/local/bin/playwright-god"
              />
              <button
                type="button"
                onClick={handleBrowseCli}
                className="rounded-md px-2 py-1 text-[11px] text-ink-700 ring-1 ring-ink-200 hover:bg-ink-50"
              >
                Browse…
              </button>
            </div>
          </Field>

          {validationError && (
            <div className="text-[12px] text-rose-700">{validationError}</div>
          )}
          {error && <div className="text-[12px] text-rose-700">{error}</div>}

          <div className="mt-2 flex items-center justify-between">
            <ResetButton onConfirm={handleReset} disabled={saving} />

            <div className="flex items-center gap-3">
              {showSaved && (
                <span
                  role="status"
                  className="text-[11px] text-emerald-700"
                >
                  Saved
                </span>
              )}
              <button
                type="submit"
                disabled={!canSave}
                className={clsx(
                  "rounded-md px-3 py-1.5 text-[12px] font-medium",
                  !canSave
                    ? "bg-ink-100 text-ink-400"
                    : "bg-accent text-white shadow-soft hover:bg-accent/90",
                )}
              >
                {saving ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        </form>
      </Panel>
    </div>
  );
}

const inputCls =
  "w-full rounded-md border border-ink-200 bg-white/70 px-3 py-1.5 text-[13px] text-ink-900 placeholder:text-ink-400 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20";

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[12px] font-medium text-ink-700">{label}</span>
      {children}
      {hint && <span className="text-[11px] text-ink-500">{hint}</span>}
    </label>
  );
}

function ProviderSelect({
  value,
  onChange,
}: {
  value: Provider;
  onChange: (p: Provider) => void;
}) {
  return (
    <Select.Root value={value} onValueChange={(v) => onChange(v as Provider)}>
      <Select.Trigger
        className="flex w-full items-center justify-between rounded-md border border-ink-200 bg-white/70 px-3 py-1.5 text-[13px] text-ink-900 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20"
        aria-label="Provider"
      >
        <Select.Value />
        <Select.Icon className="text-ink-500">▾</Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Content
          className="z-50 overflow-hidden rounded-md border border-ink-200 bg-white shadow-soft"
          position="popper"
          sideOffset={4}
        >
          <Select.Viewport className="p-1">
            {PROVIDERS.map((p) => (
              <Select.Item
                key={p}
                value={p}
                className="cursor-pointer rounded px-2 py-1 text-[13px] text-ink-800 outline-none data-[highlighted]:bg-accent/10 data-[highlighted]:text-accent"
              >
                <Select.ItemText>{p}</Select.ItemText>
              </Select.Item>
            ))}
          </Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  );
}

function ResetButton({
  onConfirm,
  disabled,
}: {
  onConfirm: () => void;
  disabled?: boolean;
}) {
  return (
    <AlertDialog.Root>
      <AlertDialog.Trigger asChild>
        <button
          type="button"
          disabled={disabled}
          className="rounded-md px-3 py-1.5 text-[12px] text-rose-700 ring-1 ring-rose-200 hover:bg-rose-50 disabled:opacity-50"
        >
          Reset to defaults
        </button>
      </AlertDialog.Trigger>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="fixed inset-0 z-40 bg-ink-900/30 backdrop-blur-sm" />
        <AlertDialog.Content
          className="fixed left-1/2 top-1/2 z-50 w-[420px] -translate-x-1/2 -translate-y-1/2 rounded-xl bg-white p-5 shadow-soft"
        >
          <AlertDialog.Title className="text-[14px] font-semibold text-ink-900">
            Reset settings?
          </AlertDialog.Title>
          <AlertDialog.Description className="mt-2 text-[12px] text-ink-600">
            This restores defaults and removes saved API keys for OpenAI,
            Anthropic, and Google from this app's secret store. Keys in your
            shell environment are not affected.
          </AlertDialog.Description>
          <div className="mt-4 flex justify-end gap-2">
            <AlertDialog.Cancel asChild>
              <button className="rounded-md px-3 py-1.5 text-[12px] text-ink-700 ring-1 ring-ink-200 hover:bg-ink-50">
                Cancel
              </button>
            </AlertDialog.Cancel>
            <AlertDialog.Action asChild>
              <button
                onClick={onConfirm}
                className="rounded-md bg-rose-600 px-3 py-1.5 text-[12px] font-medium text-white hover:bg-rose-700"
              >
                Reset
              </button>
            </AlertDialog.Action>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
}
