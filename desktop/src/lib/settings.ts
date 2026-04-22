import { invokeCommand } from "@/lib/tauri";

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

export const DEFAULT_SETTINGS: Settings = {
  provider: "openai",
  model: "",
  ollama_url: "http://localhost:11434",
  playwright_cli_timeout: 300,
  cli_path: null,
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
  return invokeCommand<Settings>("get_settings");
}

export async function saveSettings(settings: Settings): Promise<Settings> {
  return invokeCommand<Settings>("save_settings", { settings });
}

export async function resetSettings(): Promise<Settings> {
  return invokeCommand<Settings>("reset_settings");
}

export async function detectCli(): Promise<CliStatus> {
  return invokeCommand<CliStatus>("detect_cli");
}

export async function getSecret(key: string): Promise<string | null> {
  return invokeCommand<string | null>("get_secret", { key });
}

export async function setSecret(key: string, value: string): Promise<void> {
  await invokeCommand("set_secret", { key, value });
}

export async function deleteSecret(key: string): Promise<void> {
  await invokeCommand("delete_secret", { key });
}

export async function secretsHealth(): Promise<SecretsHealth> {
  return invokeCommand<SecretsHealth>("secrets_health");
}
