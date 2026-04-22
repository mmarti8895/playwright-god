import { create } from "zustand";

export type SectionId =
  | "repository"
  | "memory-map"
  | "flow-graph"
  | "coverage"
  | "rag"
  | "generation"
  | "codegen-stream"
  | "inspect"
  | "audit-log"
  | "settings";

export interface RecentRepo {
  path: string;
  openedAt: string; // ISO timestamp
}

interface UIState {
  activeSection: SectionId;
  setActiveSection: (id: SectionId) => void;

  outputPaneCollapsed: boolean;
  toggleOutputPane: () => void;
  setOutputPaneCollapsed: (collapsed: boolean) => void;

  activeRepo: string | null;
  setActiveRepo: (path: string | null) => void;

  recentRepos: RecentRepo[];
  setRecentRepos: (repos: RecentRepo[]) => void;

  /** Bumped after every successful pipeline run so viewers can re-fetch. */
  artifactsVersion: number;
  bumpArtifactsVersion: () => void;

  /** Cross-section prompt prefill (e.g. "Generate test for this gap"). */
  generationPrompt: string;
  setGenerationPrompt: (prompt: string) => void;
}

export const useUIStore = create<UIState>((set) => ({
  activeSection: "repository",
  setActiveSection: (id) => set({ activeSection: id }),

  outputPaneCollapsed: false,
  toggleOutputPane: () =>
    set((s) => ({ outputPaneCollapsed: !s.outputPaneCollapsed })),
  setOutputPaneCollapsed: (collapsed) =>
    set({ outputPaneCollapsed: collapsed }),

  activeRepo: null,
  setActiveRepo: (path) => set({ activeRepo: path }),

  recentRepos: [],
  setRecentRepos: (repos) => set({ recentRepos: repos }),

  artifactsVersion: 0,
  bumpArtifactsVersion: () =>
    set((s) => ({ artifactsVersion: s.artifactsVersion + 1 })),

  generationPrompt: "",
  setGenerationPrompt: (prompt) => set({ generationPrompt: prompt }),
}));
