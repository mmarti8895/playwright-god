//! Persistence helpers for the recent-repositories list.
//!
//! The list is stored in the app's `tauri-plugin-store` JSON store under
//! the key `recent_repos`, MRU-ordered, capped at [`MAX_RECENT`] entries.

use chrono::Utc;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tauri::{AppHandle, Runtime};
use tauri_plugin_store::StoreExt;

const STORE_PATH: &str = "settings.json";
const KEY_RECENT: &str = "recent_repos";
pub const MAX_RECENT: usize = 10;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct RecentRepo {
    pub path: String,
    #[serde(rename = "openedAt")]
    pub opened_at: String,
}

pub fn list_recent<R: Runtime>(app: &AppHandle<R>) -> anyhow::Result<Vec<RecentRepo>> {
    let store = app.store(STORE_PATH)?;
    let v = store.get(KEY_RECENT).unwrap_or(Value::Array(vec![]));
    let parsed: Vec<RecentRepo> = serde_json::from_value(v).unwrap_or_default();
    Ok(parsed)
}

pub fn add_recent<R: Runtime>(app: &AppHandle<R>, path: &str) -> anyhow::Result<Vec<RecentRepo>> {
    let store = app.store(STORE_PATH)?;
    let existing: Vec<RecentRepo> = store
        .get(KEY_RECENT)
        .and_then(|v| serde_json::from_value(v).ok())
        .unwrap_or_default();
    let next = mru_insert(existing, path);
    store.set(KEY_RECENT, serde_json::to_value(&next)?);
    store.save()?;
    Ok(next)
}

/// Pure helper: insert `path` at the front, dedupe, cap at [`MAX_RECENT`].
pub fn mru_insert(mut existing: Vec<RecentRepo>, path: &str) -> Vec<RecentRepo> {
    existing.retain(|r| r.path != path);
    existing.insert(
        0,
        RecentRepo {
            path: path.to_string(),
            opened_at: Utc::now().to_rfc3339(),
        },
    );
    if existing.len() > MAX_RECENT {
        existing.truncate(MAX_RECENT);
    }
    existing
}

#[cfg(test)]
mod tests {
    use super::*;

    fn r(p: &str) -> RecentRepo {
        RecentRepo { path: p.into(), opened_at: "2026-04-21T00:00:00Z".into() }
    }

    #[test]
    fn mru_insert_prepends_new_entry() {
        let out = mru_insert(vec![r("/a"), r("/b")], "/c");
        assert_eq!(out[0].path, "/c");
        assert_eq!(out[1].path, "/a");
        assert_eq!(out[2].path, "/b");
    }

    #[test]
    fn mru_insert_dedupes_existing_entry_to_front() {
        let out = mru_insert(vec![r("/a"), r("/b"), r("/c")], "/b");
        assert_eq!(out.len(), 3);
        assert_eq!(out[0].path, "/b");
        assert_eq!(out[1].path, "/a");
        assert_eq!(out[2].path, "/c");
    }

    #[test]
    fn mru_insert_caps_at_ten_entries() {
        let mut start: Vec<RecentRepo> = (0..MAX_RECENT)
            .map(|i| r(&format!("/p{i}")))
            .collect();
        // Add an 11th distinct entry; the oldest should be evicted.
        start = mru_insert(start, "/new");
        assert_eq!(start.len(), MAX_RECENT);
        assert_eq!(start[0].path, "/new");
        // The oldest entry ("/p9") was evicted.
        let last = format!("/p{}", MAX_RECENT - 1);
        assert!(start.iter().all(|r| r.path != last));
        // The 9th-oldest original ("/p8") is now at the tail.
        assert_eq!(start[MAX_RECENT - 1].path, "/p8");
    }
}
