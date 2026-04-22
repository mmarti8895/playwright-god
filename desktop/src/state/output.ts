import { create } from "zustand";

export type Stream = "stdout" | "stderr" | "info";

export interface OutputLine {
  id: number;
  ts: string; // ISO timestamp
  stream: Stream;
  text: string;
}

interface OutputState {
  lines: OutputLine[];
  append: (stream: Stream, text: string) => void;
  clear: () => void;
}

let nextId = 0;

const MAX_LINES = 50_000;

export const useOutputStore = create<OutputState>((set) => ({
  lines: [],
  append: (stream, text) =>
    set((s) => {
      const line: OutputLine = {
        id: nextId++,
        ts: new Date().toISOString(),
        stream,
        text,
      };
      const next = s.lines.length >= MAX_LINES
        ? [...s.lines.slice(s.lines.length - MAX_LINES + 1), line]
        : [...s.lines, line];
      return { lines: next };
    }),
  clear: () => set({ lines: [] }),
}));
