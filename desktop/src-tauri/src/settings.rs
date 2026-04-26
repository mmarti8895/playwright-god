//! Settings: non-secret app config persisted via `tauri-plugin-store`
//! (`settings.json`). Secret API keys live in the OS keyring (see `secrets`).
//!
//! The desktop's `EffectiveSettings::load` merges these two so the pipeline
//! orchestrator can build the env-var bridge described in design.md D8.

use std::collections::HashMap;
use std::path::Path;

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Runtime};
use tauri_plugin_store::StoreExt;

use crate::secrets;

const STORE_PATH: &str = "settings.json";
const KEY_SETTINGS: &str = "settings";

pub const DEFAULT_OLLAMA_URL: &str = "http://localhost:11434";
pub const DEFAULT_PLAYWRIGHT_CLI_TIMEOUT: u32 = 300;

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "kebab-case")]
pub enum SettingValueSource {
    Settings,
    RepoDotenv,
    ProcessEnv,
    Missing,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct EffectiveSettingsMeta {
    pub provider_source: SettingValueSource,
    pub model_source: SettingValueSource,
    pub openai_api_key_source: SettingValueSource,
    pub anthropic_api_key_source: SettingValueSource,
    pub google_api_key_source: SettingValueSource,
    pub selected_api_key_env: Option<String>,
    pub selected_api_key_source: SettingValueSource,
}

impl Default for EffectiveSettingsMeta {
    fn default() -> Self {
        Self {
            provider_source: SettingValueSource::Missing,
            model_source: SettingValueSource::Missing,
            openai_api_key_source: SettingValueSource::Missing,
            anthropic_api_key_source: SettingValueSource::Missing,
            google_api_key_source: SettingValueSource::Missing,
            selected_api_key_env: None,
            selected_api_key_source: SettingValueSource::Missing,
        }
    }
}

/// Fully populated settings object (UI <-> store schema).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Settings {
    pub provider: String,
    pub model: String,
    pub ollama_url: String,
    pub playwright_cli_timeout: u32,
    pub cli_path: Option<String>,
    /// Override the `--target-dir` passed to `playwright-god run`.
    /// Use this when the Playwright project root differs from the selected repo root.
    pub playwright_target_dir: Option<String>,
    pub llm_retry_max: u32,
    pub llm_retry_delay_s: f64,
}

impl Default for Settings {
    fn default() -> Self {
        Self {
            provider: "openai".into(),
            model: String::new(),
            ollama_url: DEFAULT_OLLAMA_URL.into(),
            playwright_cli_timeout: DEFAULT_PLAYWRIGHT_CLI_TIMEOUT,
            cli_path: None,
            playwright_target_dir: None,
            llm_retry_max: 3,
            llm_retry_delay_s: 2.0,
        }
    }
}

impl Settings {
    pub fn load<R: Runtime>(app: &AppHandle<R>) -> anyhow::Result<Self> {
        let store = app.store(STORE_PATH)?;
        let v = store.get(KEY_SETTINGS).unwrap_or(serde_json::Value::Null);
        let s: Settings = serde_json::from_value(v).unwrap_or_default();
        Ok(s)
    }

    pub fn save<R: Runtime>(&self, app: &AppHandle<R>) -> anyhow::Result<()> {
        let store = app.store(STORE_PATH)?;
        store.set(KEY_SETTINGS, serde_json::to_value(self)?);
        store.save()?;
        Ok(())
    }

    /// Validate user-edited fields. Returns the validated copy or the first
    /// human-readable error message.
    pub fn validate(mut self) -> Result<Self, String> {
        self.provider = self.provider.trim().to_string();
        self.model = self.model.trim().to_string();
        self.ollama_url = self.ollama_url.trim().to_string();
        self.cli_path = self.cli_path.map(|p| p.trim().to_string()).filter(|p| !p.is_empty());
        self.playwright_target_dir = self
            .playwright_target_dir
            .map(|p| p.trim().to_string())
            .filter(|p| !p.is_empty());

        const ALLOWED_PROVIDERS: &[&str] = &[
            "openai",
            "anthropic",
            "gemini",
            "ollama",
            "template",
            "playwright-cli",
        ];
        if !ALLOWED_PROVIDERS.contains(&self.provider.as_str()) {
            return Err(format!("Unknown provider: {}", self.provider));
        }
        if self.playwright_cli_timeout < 1 {
            return Err("Playwright CLI timeout must be a positive integer.".into());
        }
        if self.llm_retry_delay_s < 0.0 {
            self.llm_retry_delay_s = 0.0;
        }
        Ok(self)
    }
}

/// Non-secret + secret values merged for subprocess env injection (D8).
#[derive(Debug, Default, Clone)]
pub struct EffectiveSettings {
    pub provider: Option<String>,
    pub model: Option<String>,
    pub ollama_url: Option<String>,
    pub openai_api_key: Option<String>,
    pub anthropic_api_key: Option<String>,
    pub google_api_key: Option<String>,
    pub meta: EffectiveSettingsMeta,
}

impl EffectiveSettings {
    pub fn load<R: Runtime>(app: &AppHandle<R>) -> anyhow::Result<Self> {
        Self::load_with_repo(app, None)
    }

    pub fn load_for_repo<R: Runtime>(app: &AppHandle<R>, repo: &Path) -> anyhow::Result<Self> {
        Self::load_with_repo(app, Some(repo))
    }

    fn load_with_repo<R: Runtime>(app: &AppHandle<R>, repo: Option<&Path>) -> anyhow::Result<Self> {
        let s = Settings::load(app)?;
        let dotenv = repo
            .and_then(|repo| read_repo_dotenv(repo).ok())
            .unwrap_or_default();

        let (provider, provider_source) = resolve_value(
            blank_to_none(s.provider),
            dotenv.get("PLAYWRIGHT_GOD_PROVIDER").cloned(),
            std::env::var("PLAYWRIGHT_GOD_PROVIDER").ok(),
        );
        let (model, model_source) = resolve_value(
            blank_to_none(s.model),
            dotenv.get("PLAYWRIGHT_GOD_MODEL").cloned(),
            std::env::var("PLAYWRIGHT_GOD_MODEL").ok(),
        );
        let (ollama_url, _) = resolve_value(
            blank_to_none(s.ollama_url),
            dotenv.get("OLLAMA_URL").cloned(),
            std::env::var("OLLAMA_URL").ok(),
        );
        let (openai_api_key, openai_api_key_source) = resolve_value(
            secrets::get(app, "OPENAI_API_KEY"),
            dotenv.get("OPENAI_API_KEY").cloned(),
            std::env::var("OPENAI_API_KEY").ok(),
        );
        let (anthropic_api_key, anthropic_api_key_source) = resolve_value(
            secrets::get(app, "ANTHROPIC_API_KEY"),
            dotenv.get("ANTHROPIC_API_KEY").cloned(),
            std::env::var("ANTHROPIC_API_KEY").ok(),
        );
        let (google_api_key, google_api_key_source) = resolve_value(
            secrets::get(app, "GOOGLE_API_KEY"),
            dotenv.get("GOOGLE_API_KEY").cloned(),
            std::env::var("GOOGLE_API_KEY").ok(),
        );

        let selected_api_key_env = provider
            .as_deref()
            .and_then(provider_api_key_env)
            .map(String::from);
        let selected_api_key_source = selected_api_key_env
            .as_deref()
            .map(|env| match env {
                "OPENAI_API_KEY" => openai_api_key_source,
                "ANTHROPIC_API_KEY" => anthropic_api_key_source,
                "GOOGLE_API_KEY" => google_api_key_source,
                _ => SettingValueSource::Missing,
            })
            .unwrap_or(SettingValueSource::Missing);

        Ok(Self {
            provider,
            model,
            ollama_url,
            openai_api_key,
            anthropic_api_key,
            google_api_key,
            meta: EffectiveSettingsMeta {
                provider_source,
                model_source,
                openai_api_key_source,
                anthropic_api_key_source,
                google_api_key_source,
                selected_api_key_env,
                selected_api_key_source,
            },
        })
    }

    pub fn into_env(self) -> HashMap<String, String> {
        let mut env = HashMap::new();
        if let Some(v) = self.provider { env.insert("PLAYWRIGHT_GOD_PROVIDER".into(), v); }
        if let Some(v) = self.model { env.insert("PLAYWRIGHT_GOD_MODEL".into(), v); }
        if let Some(v) = self.openai_api_key { env.insert("OPENAI_API_KEY".into(), v); }
        if let Some(v) = self.anthropic_api_key { env.insert("ANTHROPIC_API_KEY".into(), v); }
        if let Some(v) = self.google_api_key { env.insert("GOOGLE_API_KEY".into(), v); }
        if let Some(v) = self.ollama_url { env.insert("OLLAMA_URL".into(), v); }
        env
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct EffectiveSettingsSummary {
    pub provider: Option<String>,
    pub provider_source: SettingValueSource,
    pub model: Option<String>,
    pub model_source: SettingValueSource,
    pub selected_api_key_env: Option<String>,
    pub selected_api_key_source: SettingValueSource,
    pub selected_api_key_present: bool,
}

#[tauri::command]
pub fn get_effective_settings_summary<R: Runtime>(
    app: AppHandle<R>,
    repo: Option<String>,
) -> Result<EffectiveSettingsSummary, String> {
    let effective = match repo {
        Some(path) if !path.trim().is_empty() => {
            EffectiveSettings::load_for_repo(&app, Path::new(path.trim()))
        }
        _ => EffectiveSettings::load(&app),
    }
    .map_err(|e| e.to_string())?;

    let selected_api_key_present = effective
        .meta
        .selected_api_key_env
        .as_deref()
        .map(|env| match env {
            "OPENAI_API_KEY" => effective.openai_api_key.is_some(),
            "ANTHROPIC_API_KEY" => effective.anthropic_api_key.is_some(),
            "GOOGLE_API_KEY" => effective.google_api_key.is_some(),
            _ => false,
        })
        .unwrap_or(false);

    Ok(EffectiveSettingsSummary {
        provider: effective.provider,
        provider_source: effective.meta.provider_source,
        model: effective.model,
        model_source: effective.meta.model_source,
        selected_api_key_env: effective.meta.selected_api_key_env,
        selected_api_key_source: effective.meta.selected_api_key_source,
        selected_api_key_present,
    })
}

fn blank_to_none(s: String) -> Option<String> {
    let t = s.trim();
    if t.is_empty() { None } else { Some(t.to_string()) }
}

fn normalize_value(value: Option<String>) -> Option<String> {
    value.and_then(|v| {
        let trimmed = v.trim();
        if trimmed.is_empty() {
            None
        } else {
            Some(trimmed.to_string())
        }
    })
}

fn resolve_value(
    settings: Option<String>,
    repo_dotenv: Option<String>,
    process_env: Option<String>,
) -> (Option<String>, SettingValueSource) {
    if let Some(v) = normalize_value(settings) {
        return (Some(v), SettingValueSource::Settings);
    }
    if let Some(v) = normalize_value(repo_dotenv) {
        return (Some(v), SettingValueSource::RepoDotenv);
    }
    if let Some(v) = normalize_value(process_env) {
        return (Some(v), SettingValueSource::ProcessEnv);
    }
    (None, SettingValueSource::Missing)
}

fn provider_api_key_env(provider: &str) -> Option<&'static str> {
    match provider {
        "openai" => Some("OPENAI_API_KEY"),
        "anthropic" => Some("ANTHROPIC_API_KEY"),
        "gemini" => Some("GOOGLE_API_KEY"),
        _ => None,
    }
}

fn read_repo_dotenv(repo: &Path) -> anyhow::Result<HashMap<String, String>> {
    let path = repo.join(".env");
    if !path.exists() {
        return Ok(HashMap::new());
    }
    let content = std::fs::read_to_string(path)?;
    Ok(parse_dotenv(&content))
}

fn parse_dotenv(content: &str) -> HashMap<String, String> {
    let mut map = HashMap::new();
    for raw in content.lines() {
        let line = raw.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let line = line.strip_prefix("export ").unwrap_or(line).trim();
        let Some((key, value)) = line.split_once('=') else {
            continue;
        };
        let k = key.trim();
        if k.is_empty() {
            continue;
        }
        let mut v = value.trim().to_string();
        if (v.starts_with('"') && v.ends_with('"')) || (v.starts_with('\'') && v.ends_with('\'')) {
            if v.len() >= 2 {
                v = v[1..v.len() - 1].to_string();
            }
        }
        map.insert(k.to_string(), v);
    }
    map
}

// --- Tauri commands ---

#[tauri::command]
pub fn get_settings<R: Runtime>(app: AppHandle<R>) -> Result<Settings, String> {
    Settings::load(&app).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn save_settings<R: Runtime>(app: AppHandle<R>, settings: Settings) -> Result<Settings, String> {
    let validated = settings.validate()?;
    validated.save(&app).map_err(|e| e.to_string())?;
    Ok(validated)
}

/// Reset persisted settings + delete known API-key secrets. Returns the new
/// (default) settings.
#[tauri::command]
pub fn reset_settings<R: Runtime>(app: AppHandle<R>) -> Result<Settings, String> {
    let defaults = Settings::default();
    defaults.save(&app).map_err(|e| e.to_string())?;
    for k in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"] {
        let _ = secrets::delete(&app, k);
    }
    Ok(defaults)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn validate_rejects_unknown_provider() {
        let s = Settings { provider: "evilcorp".into(), ..Default::default() };
        assert!(s.validate().is_err());
    }

    #[test]
    fn validate_rejects_zero_timeout() {
        let s = Settings { playwright_cli_timeout: 0, ..Default::default() };
        assert!(s.validate().is_err());
    }

    #[test]
    fn validate_trims_and_blanks_cli_path() {
        let s = Settings { cli_path: Some("   ".into()), ..Default::default() };
        let v = s.validate().unwrap();
        assert!(v.cli_path.is_none());
    }

    #[test]
    fn into_env_emits_only_set_keys() {
        let s = EffectiveSettings {
            provider: Some("openai".into()),
            model: Some("gpt-4o".into()),
            openai_api_key: Some("sk-xxx".into()),
            meta: EffectiveSettingsMeta::default(),
            ..Default::default()
        };
        let env = s.into_env();
        assert_eq!(env.get("PLAYWRIGHT_GOD_PROVIDER").unwrap(), "openai");
        assert_eq!(env.get("OPENAI_API_KEY").unwrap(), "sk-xxx");
        assert!(!env.contains_key("ANTHROPIC_API_KEY"));
        assert!(!env.contains_key("OLLAMA_URL"));
    }

    #[test]
    fn settings_round_trip_through_serde_json() {
        let s = Settings {
            provider: "anthropic".into(),
            model: "claude-3-5-sonnet".into(),
            ollama_url: "http://example.local:11434".into(),
            playwright_cli_timeout: 600,
            cli_path: Some("/usr/local/bin/playwright-god".into()),
            llm_retry_max: 5,
            llm_retry_delay_s: 1.5,
            ..Default::default()
        };
        let v = serde_json::to_value(&s).unwrap();
        let back: Settings = serde_json::from_value(v).unwrap();
        assert_eq!(back.provider, "anthropic");
        assert_eq!(back.model, "claude-3-5-sonnet");
        assert_eq!(back.playwright_cli_timeout, 600);
        assert_eq!(back.cli_path.as_deref(), Some("/usr/local/bin/playwright-god"));
        assert_eq!(back.llm_retry_max, 5);
        assert_eq!(back.llm_retry_delay_s, 1.5);
    }

    #[test]
    fn validate_clamps_negative_retry_delay() {
        let s = Settings { llm_retry_delay_s: -1.0, ..Default::default() };
        let v = s.validate().unwrap();
        assert_eq!(v.llm_retry_delay_s, 0.0);
    }

    #[test]
    fn settings_default_validates_clean() {
        let v = Settings::default().validate().unwrap();
        assert_eq!(v.provider, "openai");
        assert_eq!(v.playwright_cli_timeout, DEFAULT_PLAYWRIGHT_CLI_TIMEOUT);
    }

    #[test]
    fn into_env_emits_ollama_url_when_set() {
        let s = EffectiveSettings {
            ollama_url: Some("http://localhost:11434".into()),
            meta: EffectiveSettingsMeta::default(),
            ..Default::default()
        };
        let env = s.into_env();
        assert_eq!(env.get("OLLAMA_URL").unwrap(), "http://localhost:11434");
    }

    #[test]
    fn resolve_value_prefers_settings_over_repo_and_env() {
        let (value, source) = resolve_value(
            Some("gpt-5.4".into()),
            Some("repo-model".into()),
            Some("env-model".into()),
        );
        assert_eq!(value.as_deref(), Some("gpt-5.4"));
        assert_eq!(source, SettingValueSource::Settings);
    }

    #[test]
    fn resolve_value_uses_repo_before_process_env() {
        let (value, source) = resolve_value(None, Some("repo-model".into()), Some("env-model".into()));
        assert_eq!(value.as_deref(), Some("repo-model"));
        assert_eq!(source, SettingValueSource::RepoDotenv);
    }

    #[test]
    fn parse_dotenv_reads_provider_model_and_openai_key() {
        let parsed = parse_dotenv(
            "OPENAI_API_KEY=sk-test\nPLAYWRIGHT_GOD_MODEL=gpt-5.4\nPLAYWRIGHT_GOD_PROVIDER=openai\n",
        );
        assert_eq!(parsed.get("OPENAI_API_KEY").map(String::as_str), Some("sk-test"));
        assert_eq!(parsed.get("PLAYWRIGHT_GOD_MODEL").map(String::as_str), Some("gpt-5.4"));
        assert_eq!(parsed.get("PLAYWRIGHT_GOD_PROVIDER").map(String::as_str), Some("openai"));
    }

    #[test]
    fn provider_api_key_env_maps_openai() {
        assert_eq!(provider_api_key_env("openai"), Some("OPENAI_API_KEY"));
        assert_eq!(provider_api_key_env("template"), None);
    }
}
