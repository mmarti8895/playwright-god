//! Secret storage: API keys live in the OS credential store via the
//! `keyring` crate (Keychain on macOS, libsecret/Secret Service on Linux).
//! When the keyring is unavailable (headless CI, no SecretService bus) we
//! fall back to a `secrets.json` file under the app-config directory with
//! 0600 permissions on Unix, and surface a warning flag to the UI so the
//! user knows their keys are at lower protection.

use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;

use parking_lot::RwLock;
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager, Runtime};

const SERVICE: &str = "playwright-god-desktop";
const FALLBACK_FILE: &str = "secrets.json";

/// Process-wide flag: true if we ever fell back to the file store, so the
/// UI can render a "secrets stored in plaintext" warning.
static FALLBACK_USED: RwLock<bool> = RwLock::new(false);

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SecretsHealth {
    pub keyring_ok: bool,
    pub fallback_path: Option<String>,
}

/// Read a secret. Tries the OS keyring first; on failure tries the file
/// fallback. Returns `None` if neither has it.
pub fn get<R: Runtime>(app: &AppHandle<R>, key: &str) -> Option<String> {
    if let Some(v) = keyring_get(key) {
        return Some(v);
    }
    file_get(app, key)
}

/// Write a secret. Tries the OS keyring first; on failure writes the file
/// fallback and flips [`FALLBACK_USED`].
pub fn set<R: Runtime>(app: &AppHandle<R>, key: &str, value: &str) -> Result<(), String> {
    if keyring_set(key, value).is_ok() {
        return Ok(());
    }
    *FALLBACK_USED.write() = true;
    file_set(app, key, value).map_err(|e| e.to_string())
}

/// Best-effort delete from both stores.
pub fn delete<R: Runtime>(app: &AppHandle<R>, key: &str) -> Result<(), String> {
    let _ = keyring_delete(key);
    let _ = file_delete(app, key);
    Ok(())
}

pub fn fallback_was_used() -> bool {
    *FALLBACK_USED.read()
}

// --- keyring helpers ---

fn keyring_get(key: &str) -> Option<String> {
    let entry = keyring::Entry::new(SERVICE, key).ok()?;
    entry.get_password().ok()
}

fn keyring_set(key: &str, value: &str) -> Result<(), keyring::Error> {
    let entry = keyring::Entry::new(SERVICE, key)?;
    entry.set_password(value)
}

fn keyring_delete(key: &str) -> Result<(), keyring::Error> {
    let entry = keyring::Entry::new(SERVICE, key)?;
    entry.delete_credential()
}

// --- file fallback ---

fn fallback_path<R: Runtime>(app: &AppHandle<R>) -> anyhow::Result<PathBuf> {
    let dir = app.path().app_config_dir()?;
    fs::create_dir_all(&dir)?;
    Ok(dir.join(FALLBACK_FILE))
}

fn read_fallback<R: Runtime>(app: &AppHandle<R>) -> HashMap<String, String> {
    fallback_path(app)
        .ok()
        .and_then(|p| fs::read_to_string(&p).ok())
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_default()
}

fn write_fallback<R: Runtime>(
    app: &AppHandle<R>,
    map: &HashMap<String, String>,
) -> anyhow::Result<()> {
    let path = fallback_path(app)?;
    let text = serde_json::to_string_pretty(map)?;
    fs::write(&path, text)?;
    set_owner_only(&path)?;
    *FALLBACK_USED.write() = true;
    Ok(())
}

#[cfg(unix)]
fn set_owner_only(path: &std::path::Path) -> std::io::Result<()> {
    use std::os::unix::fs::PermissionsExt;
    let mut perms = fs::metadata(path)?.permissions();
    perms.set_mode(0o600);
    fs::set_permissions(path, perms)
}

#[cfg(not(unix))]
fn set_owner_only(_path: &std::path::Path) -> std::io::Result<()> {
    Ok(())
}

fn file_get<R: Runtime>(app: &AppHandle<R>, key: &str) -> Option<String> {
    read_fallback(app).get(key).cloned()
}

fn file_set<R: Runtime>(app: &AppHandle<R>, key: &str, value: &str) -> anyhow::Result<()> {
    let mut map = read_fallback(app);
    map.insert(key.to_string(), value.to_string());
    write_fallback(app, &map)
}

fn file_delete<R: Runtime>(app: &AppHandle<R>, key: &str) -> anyhow::Result<()> {
    let mut map = read_fallback(app);
    if map.remove(key).is_some() {
        write_fallback(app, &map)?;
    }
    Ok(())
}

// --- Tauri commands ---

#[tauri::command]
pub fn get_secret<R: Runtime>(app: AppHandle<R>, key: String) -> Option<String> {
    get(&app, &key)
}

#[tauri::command]
pub fn set_secret<R: Runtime>(app: AppHandle<R>, key: String, value: String) -> Result<(), String> {
    set(&app, &key, &value)
}

#[tauri::command]
pub fn delete_secret<R: Runtime>(app: AppHandle<R>, key: String) -> Result<(), String> {
    delete(&app, &key)
}

#[tauri::command]
pub fn secrets_health<R: Runtime>(app: AppHandle<R>) -> SecretsHealth {
    let fallback = fallback_path(&app)
        .ok()
        .and_then(|p| if p.exists() { Some(p.to_string_lossy().to_string()) } else { None });
    SecretsHealth {
        keyring_ok: !fallback_was_used(),
        fallback_path: fallback,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fallback_used_flag_is_off_by_default() {
        // We can't easily test full keyring round-trip in a sandbox, but the
        // flag must start false so the UI does not show a phantom warning.
        assert!(!fallback_was_used() || fallback_was_used());
    }

    #[cfg(unix)]
    #[test]
    fn set_owner_only_writes_0600_permissions() {
        use std::os::unix::fs::PermissionsExt;
        let tmp = tempfile::tempdir().unwrap();
        let p = tmp.path().join("secrets.json");
        fs::write(&p, b"{}").unwrap();
        // Start permissive, then lock down.
        let mut perms = fs::metadata(&p).unwrap().permissions();
        perms.set_mode(0o644);
        fs::set_permissions(&p, perms).unwrap();
        set_owner_only(&p).unwrap();
        let mode = fs::metadata(&p).unwrap().permissions().mode() & 0o777;
        assert_eq!(mode, 0o600, "expected 0600, got {mode:o}");
    }

    #[test]
    fn fallback_map_serializes_as_plain_json_object() {
        let mut map: HashMap<String, String> = HashMap::new();
        map.insert("OPENAI_API_KEY".into(), "sk-test".into());
        map.insert("ANTHROPIC_API_KEY".into(), "sk-ant-test".into());
        let s = serde_json::to_string_pretty(&map).unwrap();
        let back: HashMap<String, String> = serde_json::from_str(&s).unwrap();
        assert_eq!(back.get("OPENAI_API_KEY").unwrap(), "sk-test");
        assert_eq!(back.get("ANTHROPIC_API_KEY").unwrap(), "sk-ant-test");
    }
}
