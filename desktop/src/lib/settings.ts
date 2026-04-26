import { invokeCommand, inTauri } from "@/lib/tauri";

export const PROVIDERS = [
  "openai",
  "anthropic",
  "gemini",
  "ollama",
  "template",
  "playwright-cli",
] as const;

export type Provider = (typeof PROVIDERS)[number];

export interface Settings {
  provider: Provider;
  model: string;
  ollama_url: string;
  playwright_cli_timeout: number;
  cli_path: string | null;
  /** Override --target-dir for `playwright-god run`. Set when the Playwright project root differs from the repo root. */
  playwright_target_dir: string | null;
  /** Maximum number of LLM call attempts (including the first). 0 disables retry. */
  llm_retry_max: number;
  /** Initial backoff delay in seconds for LLM retries. */
  llm_retry_delay_s: number;
}

export interface CliStatus {
  found: boolean;
  path: string | null;
  source: "settings" | "PATH" | "missing";
}

export interface SecretsHealth {
  keyring_ok: boolean;
  fallback_path: string | null;
}

export type SettingValueSource =
  | "settings"
  | "repo-dotenv"
  | "process-env"
  | "missing";

export interface EffectiveSettingsSummary {
  provider: string | null;
  provider_source: SettingValueSource;
  model: string | null;
  model_source: SettingValueSource;
  selected_api_key_env: string | null;
  selected_api_key_source: SettingValueSource;
  selected_api_key_present: boolean;
}

export const DEFAULT_SETTINGS: Settings = {
  provider: "openai",
  model: "",
  ollama_url: "http://localhost:11434",
  playwright_cli_timeout: 300,
  cli_path: null,
  playwright_target_dir: null,
  llm_retry_max: 3,
  llm_retry_delay_s: 2.0,
};

export function apiKeyEnvVar(provider: Provider): string | null {
  switch (provider) {
    case "openai":
      return "OPENAI_API_KEY";
    case "anthropic":
      return "ANTHROPIC_API_KEY";
    case "gemini":
      return "GOOGLE_API_KEY";
    default:
      return null;
  }
}

export function validateSettings(settings: Settings): string | null {
  if (!PROVIDERS.includes(settings.provider)) {
    return `Unknown provider: ${settings.provider}`;
  }
  if (settings.playwright_cli_timeout < 1) {
    return "Playwright CLI timeout must be a positive integer.";
  }
  return null;
}

export async function getSettings(): Promise<Settings> {
  if (!inTauri()) return DEFAULT_SETTINGS;
  return invokeCommand<Settings>("get_settings");
}

export async function saveSettings(settings: Settings): Promise<Settings> {
  if (!inTauri()) return settings;
  return invokeCommand<Settings>("save_settings", { settings });
}

export async function resetSettings(): Promise<Settings> {
  if (!inTauri()) return DEFAULT_SETTINGS;
  return invokeCommand<Settings>("reset_settings");
}

export async function detectCli(): Promise<CliStatus> {
  if (!inTauri()) return { found: false, path: null, source: "missing" };
  return invokeCommand<CliStatus>("detect_cli");
}

export async function getSecret(key: string): Promise<string | null> {
  if (!inTauri()) return null;
  return invokeCommand<string | null>("get_secret", { key });
}

export async function setSecret(key: string, value: string): Promise<void> {
  if (!inTauri()) return;
  await invokeCommand("set_secret", { key, value });
}

export async function deleteSecret(key: string): Promise<void> {
  if (!inTauri()) return;
  await invokeCommand("delete_secret", { key });
}

export async function secretsHealth(): Promise<SecretsHealth> {
  if (!inTauri()) return { keyring_ok: true, fallback_path: null };
  return invokeCommand<SecretsHealth>("secrets_health");
}

export async function getEffectiveSettingsSummary(
  repo?: string | null,
): Promise<EffectiveSettingsSummary> {
  if (!inTauri()) {
    const provider = DEFAULT_SETTINGS.provider;
    const model = DEFAULT_SETTINGS.model || null;
    return {
      provider,
      provider_source: "settings",
      model,
      model_source: model ? "settings" : "missing",
      selected_api_key_env: apiKeyEnvVar(provider),
      selected_api_key_source: "missing",
      selected_api_key_present: false,
    };
  }
  return invokeCommand<EffectiveSettingsSummary>(
    "get_effective_settings_summary",
    { repo: repo ?? null },
  );
}
