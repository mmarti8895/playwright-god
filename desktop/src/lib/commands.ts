import type { RecentRepo } from "@/state/ui";
import { invokeCommand, inTauri } from "@/lib/tauri";

export async function pickRepository(): Promise<string | null> {
  if (!inTauri()) return null;
  return invokeCommand<string | null>("pick_repository");
}

export async function listRecentRepos(): Promise<RecentRepo[]> {
  if (!inTauri()) return [];
  return invokeCommand<RecentRepo[]>("list_recent_repos");
}

export async function addRecentRepo(path: string): Promise<RecentRepo[]> {
  if (!inTauri()) return [];
  return invokeCommand<RecentRepo[]>("add_recent_repo", { path });
}

export async function getOutputPaneCollapsed(): Promise<boolean> {
  if (!inTauri()) return false;
  return invokeCommand<boolean>("get_output_pane_collapsed");
}

export async function setOutputPaneCollapsed(collapsed: boolean): Promise<void> {
  if (!inTauri()) return;
  await invokeCommand("set_output_pane_collapsed", { collapsed });
}
