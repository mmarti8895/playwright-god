//! Settings: non-secret app config persisted via `tauri-plugin-store`
//! (`settings.json`). Secret API keys live in the OS keyring (see `secrets`).
//!
//! The desktop's `EffectiveSettings::load` merges these two so the pipeline
//! orchestrator can build the env-var bridge described in design.md D8.

use std::collections::HashMap;

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Runtime};
use tauri_plugin_store::StoreExt;

use crate::secrets;

const STORE_PATH: &str = "settings.json";
const KEY_SETTINGS: &str = "settings";

pub const DEFAULT_OLLAMA_URL: &str = "http://localhost:11434";
pub const DEFAULT_PLAYWRIGHT_CLI_TIMEOUT: u32 = 300;

/// Fully populated settings object (UI <-> store schema).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Settings {
    pub provider: String,
    pub model: String,
    pub ollama_url: String,
    pub playwright_cli_timeout: u32,
    pub cli_path: Option<String>,
}

impl Default for Settings {
    fn default() -> Self {
        Self {
            provider: "openai".into(),
            model: String::new(),
            ollama_url: DEFAULT_OLLAMA_URL.into(),
            playwright_cli_timeout: DEFAULT_PLAYWRIGHT_CLI_TIMEOUT,
            cli_path: None,
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
}

impl EffectiveSettings {
    pub fn load<R: Runtime>(app: &AppHandle<R>) -> anyhow::Result<Self> {
        let s = Settings::load(app)?;
        Ok(Self {
            provider: blank_to_none(s.provider),
            model: blank_to_none(s.model),
            ollama_url: blank_to_none(s.ollama_url),
            openai_api_key: secrets::get(app, "OPENAI_API_KEY")
                .or_else(|| std::env::var("OPENAI_API_KEY").ok()),
            anthropic_api_key: secrets::get(app, "ANTHROPIC_API_KEY")
                .or_else(|| std::env::var("ANTHROPIC_API_KEY").ok()),
            google_api_key: secrets::get(app, "GOOGLE_API_KEY")
                .or_else(|| std::env::var("GOOGLE_API_KEY").ok()),
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

fn blank_to_none(s: String) -> Option<String> {
    let t = s.trim();
    if t.is_empty() { None } else { Some(t.to_string()) }
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
        };
        let v = serde_json::to_value(&s).unwrap();
        let back: Settings = serde_json::from_value(v).unwrap();
        assert_eq!(back.provider, "anthropic");
        assert_eq!(back.model, "claude-3-5-sonnet");
        assert_eq!(back.playwright_cli_timeout, 600);
        assert_eq!(back.cli_path.as_deref(), Some("/usr/local/bin/playwright-god"));
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
            ..Default::default()
        };
        let env = s.into_env();
        assert_eq!(env.get("OLLAMA_URL").unwrap(), "http://localhost:11434");
    }
}
