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

export interface FlowGraphFocus {
  query: string;
}

export type CoverageRunStatus = "idle" | "running" | "done" | "error";

export interface CoverageRunState {
  status: CoverageRunStatus;
  logLines: string[];
  errorMessage: string | null;
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

  /** One-time Flow Graph focus handoff from other sections. */
  flowGraphFocus: FlowGraphFocus | null;
  setFlowGraphFocus: (focus: FlowGraphFocus | null) => void;
  consumeFlowGraphFocus: () => FlowGraphFocus | null;

  /** Coverage run lifecycle state (persists across navigation). */
  coverageRun: CoverageRunState;
  setCoverageRunStatus: (status: CoverageRunStatus) => void;
  /** Append a log line; silently drops oldest lines when cap of 500 is reached. */
  appendCoverageLogLine: (line: string) => void;
  /** Reset to idle state, clearing log and error. */
  clearCoverageRun: () => void;
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

  flowGraphFocus: null,
  setFlowGraphFocus: (focus) => set({ flowGraphFocus: focus }),
  consumeFlowGraphFocus: () => {
    let consumed: FlowGraphFocus | null = null;
    set((s) => {
      consumed = s.flowGraphFocus;
      return { flowGraphFocus: null };
    });
    return consumed;
  },

  coverageRun: { status: "idle", logLines: [], errorMessage: null },
  setCoverageRunStatus: (status) =>
    set((s) => ({
      coverageRun: {
        ...s.coverageRun,
        status,
        errorMessage: status === "idle" ? null : s.coverageRun.errorMessage,
      },
    })),
  appendCoverageLogLine: (line) =>
    set((s) => {
      const MAX = 500;
      const lines = s.coverageRun.logLines;
      const next = lines.length >= MAX ? [...lines.slice(1), line] : [...lines, line];
      return { coverageRun: { ...s.coverageRun, logLines: next } };
    }),
  clearCoverageRun: () =>
    set({ coverageRun: { status: "idle", logLines: [], errorMessage: null } }),
}));
