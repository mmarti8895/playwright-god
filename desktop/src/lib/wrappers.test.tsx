import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";

const {
  invokeMock,
  isTauriMock,
  saveMock,
  writeTextFileMock,
  MockChannel,
} = vi.hoisted(() => ({
  invokeMock: vi.fn(),
  isTauriMock: vi.fn(),
  saveMock: vi.fn(),
  writeTextFileMock: vi.fn(),
  MockChannel: class MockChannel<T> {
    onmessage?: (response: T) => void;
  },
}));

vi.mock("@tauri-apps/api/core", () => ({
  invoke: invokeMock,
  isTauri: isTauriMock,
  Channel: MockChannel,
}));

vi.mock("@tauri-apps/plugin-dialog", () => ({
  save: saveMock,
}));

vi.mock("@tauri-apps/plugin-fs", () => ({
  writeTextFile: writeTextFileMock,
}));

import {
  addRecentRepo,
  getOutputPaneCollapsed,
  listRecentRepos,
  pickRepository,
  setOutputPaneCollapsed,
} from "@/lib/commands";
import {
  ragSearch,
  readCoverage,
  readFlowGraph,
  readMemoryMap,
} from "@/lib/artifacts";
import {
  apiKeyEnvVar,
  DEFAULT_SETTINGS,
  detectCli,
  getSecret,
  getSettings,
  resetSettings,
  saveSettings,
  secretsHealth,
  setSecret,
  deleteSecret,
  validateSettings,
} from "@/lib/settings";
import {
  discoverRepo,
  inspectRepo,
  listRuns,
  previewPrompt,
  tailCodegen,
} from "@/lib/runs";
import { exportRows } from "@/lib/csv";
import { usePlatform } from "@/lib/platform";

describe("desktop wrapper modules", () => {
  beforeEach(() => {
    invokeMock.mockReset();
    isTauriMock.mockReset();
    saveMock.mockReset();
    writeTextFileMock.mockReset();
    isTauriMock.mockReturnValue(true);
  });

  it("commands wrappers invoke the expected backend commands", async () => {
    invokeMock
      .mockResolvedValueOnce("/repo")
      .mockResolvedValueOnce([{ path: "/repo", openedAt: "now" }])
      .mockResolvedValueOnce([{ path: "/repo", openedAt: "now" }])
      .mockResolvedValueOnce(true)
      .mockResolvedValueOnce(undefined);

    await expect(pickRepository()).resolves.toBe("/repo");
    await expect(listRecentRepos()).resolves.toEqual([{ path: "/repo", openedAt: "now" }]);
    await expect(addRecentRepo("/repo")).resolves.toEqual([{ path: "/repo", openedAt: "now" }]);
    await expect(getOutputPaneCollapsed()).resolves.toBe(true);
    await expect(setOutputPaneCollapsed(true)).resolves.toBeUndefined();

    expect(invokeMock).toHaveBeenNthCalledWith(1, "pick_repository", undefined);
    expect(invokeMock).toHaveBeenNthCalledWith(2, "list_recent_repos", undefined);
    expect(invokeMock).toHaveBeenNthCalledWith(3, "add_recent_repo", { path: "/repo" });
    expect(invokeMock).toHaveBeenNthCalledWith(4, "get_output_pane_collapsed", undefined);
    expect(invokeMock).toHaveBeenNthCalledWith(5, "set_output_pane_collapsed", { collapsed: true });
  });

  it("commands wrappers return safe fallbacks outside Tauri", async () => {
    isTauriMock.mockReturnValue(false);

    await expect(listRecentRepos()).resolves.toEqual([]);
    await expect(addRecentRepo("/repo")).resolves.toEqual([]);
    await expect(getOutputPaneCollapsed()).resolves.toBe(false);
    await expect(setOutputPaneCollapsed(true)).resolves.toBeUndefined();

    expect(invokeMock).not.toHaveBeenCalled();
  });

  it("artifacts wrappers return backend values and normalize search success", async () => {
    invokeMock
      .mockResolvedValueOnce({ total_files: 1 })
      .mockResolvedValueOnce({ nodes: [], edges: [] })
      .mockResolvedValueOnce({ totals: { percent: 100 } })
      .mockResolvedValueOnce([{ file: "src/a.ts", score: 0.8, content: "x" }]);

    await expect(readMemoryMap("/repo")).resolves.toEqual({ total_files: 1 });
    await expect(readFlowGraph("/repo")).resolves.toEqual({ nodes: [], edges: [] });
    await expect(readCoverage("/repo")).resolves.toEqual({ totals: { percent: 100 } });
    await expect(ragSearch("/repo", "query", 3)).resolves.toEqual({
      hits: [{ file: "src/a.ts", score: 0.8, content: "x" }],
      error: null,
    });
  });

  it("ragSearch stringifies non-Error backend failures", async () => {
    invokeMock.mockRejectedValueOnce("missing index");

    await expect(ragSearch("/repo", "query", 3)).resolves.toEqual({
      hits: [],
      error: "missing index",
    });
  });

  it("settings helpers cover provider/env mapping and command wrappers", async () => {
    invokeMock
      .mockResolvedValueOnce(DEFAULT_SETTINGS)
      .mockResolvedValueOnce(DEFAULT_SETTINGS)
      .mockResolvedValueOnce(DEFAULT_SETTINGS)
      .mockResolvedValueOnce({ found: true, path: "pg", source: "PATH" })
      .mockResolvedValueOnce("sekret")
      .mockResolvedValueOnce(undefined)
      .mockResolvedValueOnce(undefined)
      .mockResolvedValueOnce({ keyring_ok: true, fallback_path: null });

    expect(apiKeyEnvVar("openai")).toBe("OPENAI_API_KEY");
    expect(apiKeyEnvVar("anthropic")).toBe("ANTHROPIC_API_KEY");
    expect(apiKeyEnvVar("gemini")).toBe("GOOGLE_API_KEY");
    expect(apiKeyEnvVar("template")).toBeNull();
    expect(validateSettings({ ...DEFAULT_SETTINGS, provider: "invalid" as never })).toContain(
      "Unknown provider",
    );
    expect(validateSettings({ ...DEFAULT_SETTINGS, playwright_cli_timeout: 0 })).toContain("positive integer");
    expect(validateSettings(DEFAULT_SETTINGS)).toBeNull();

    await expect(getSettings()).resolves.toEqual(DEFAULT_SETTINGS);
    await expect(saveSettings(DEFAULT_SETTINGS)).resolves.toEqual(DEFAULT_SETTINGS);
    await expect(resetSettings()).resolves.toEqual(DEFAULT_SETTINGS);
    await expect(detectCli()).resolves.toEqual({ found: true, path: "pg", source: "PATH" });
    await expect(getSecret("OPENAI_API_KEY")).resolves.toBe("sekret");
    await expect(setSecret("OPENAI_API_KEY", "sekret")).resolves.toBeUndefined();
    await expect(deleteSecret("OPENAI_API_KEY")).resolves.toBeUndefined();
    await expect(secretsHealth()).resolves.toEqual({ keyring_ok: true, fallback_path: null });
  });

  it("runs wrappers invoke backend commands and tailCodegen handles stop and errors", async () => {
    const onEvent = vi.fn();
    invokeMock
      .mockResolvedValueOnce([{ run_id: "r1" }])
      .mockResolvedValueOnce({ ok: true })
      .mockResolvedValueOnce({ ok: true })
      .mockResolvedValueOnce({ prompt: "hello" })
      .mockRejectedValueOnce(new Error("tail failed"));

    await expect(listRuns("/repo")).resolves.toEqual([{ run_id: "r1" }]);
    await expect(inspectRepo("/repo")).resolves.toEqual({ ok: true });
    await expect(discoverRepo("/repo")).resolves.toEqual({ ok: true });
    await expect(previewPrompt("/repo", "login flow")).resolves.toEqual({ prompt: "hello" });

    const handle = tailCodegen("/repo", "run-1", onEvent);
    expect(invokeMock).toHaveBeenLastCalledWith("tail_codegen", {
      repo: "/repo",
      runId: "run-1",
      onEvent: expect.any(MockChannel),
    });
    await waitFor(() => {
      expect(onEvent).toHaveBeenCalledWith({ type: "stopped" });
    });

    handle.stop();
    expect(onEvent).toHaveBeenCalledTimes(1);
  });

  it("tailCodegen emits stopped immediately outside Tauri", () => {
    isTauriMock.mockReturnValue(false);
    const onEvent = vi.fn();
    const handle = tailCodegen("/repo", "run-1", onEvent);
    handle.stop();
    expect(onEvent).toHaveBeenCalledWith({ type: "stopped" });
  });

  it("tailCodegen forwards channel events until it is stopped", () => {
    const onEvent = vi.fn();
    invokeMock.mockResolvedValueOnce(undefined);

    const handle = tailCodegen("/repo", "run-2", onEvent);
    const channel = invokeMock.mock.calls[0]?.[1]?.onEvent as InstanceType<typeof MockChannel>;

    channel.onmessage?.({ type: "tick" });
    expect(onEvent).toHaveBeenNthCalledWith(1, { type: "tick" });

    handle.stop();
    channel.onmessage?.({ type: "stdout-line", line: "after stop" });
    expect(onEvent).toHaveBeenNthCalledWith(2, { type: "stopped" });
    expect(onEvent).toHaveBeenCalledTimes(2);
  });

  it("exportRows covers browser and Tauri flows", async () => {
    const anchor = {
      click: vi.fn(),
      remove: vi.fn(),
      href: "",
      download: "",
    } as unknown as HTMLAnchorElement;
    const originalCreateElement = document.createElement.bind(document);
    const createElementSpy = vi.spyOn(document, "createElement").mockImplementation((tagName) => {
      if (tagName === "a") {
        return anchor;
      }
      return originalCreateElement(tagName);
    });
    const appendSpy = vi.spyOn(document.body, "appendChild").mockImplementation(() => anchor);
    const createObjectURL = vi.fn(() => "blob:demo");
    const revokeObjectURL = vi.fn();
    const originalCreateObjectURL = URL.createObjectURL;
    const originalRevokeObjectURL = URL.revokeObjectURL;
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      writable: true,
      value: createObjectURL,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      writable: true,
      value: revokeObjectURL,
    });

    try {
      isTauriMock.mockReturnValue(false);
      await expect(
        exportRows([{ a: 1 }], [{ header: "a", value: (row) => row.a }], "demo.csv"),
      ).resolves.toEqual({ message: "Downloaded demo.csv." });

      isTauriMock.mockReturnValue(true);
      saveMock.mockResolvedValueOnce(null).mockResolvedValueOnce("C:/tmp/demo.csv");
      writeTextFileMock.mockResolvedValueOnce(undefined);

      await expect(
        exportRows([{ a: 1 }], [{ header: "a", value: (row) => row.a }], "demo.csv"),
      ).resolves.toEqual({ message: "Export cancelled." });
      await expect(
        exportRows([{ a: 1 }], [{ header: "a", value: (row) => row.a }], "demo.csv"),
      ).resolves.toEqual({ message: "Exported 1 rows to C:/tmp/demo.csv." });

      expect(writeTextFileMock).toHaveBeenCalledWith(
        "C:/tmp/demo.csv",
        expect.stringContaining("a"),
      );
    } finally {
      createElementSpy.mockRestore();
      appendSpy.mockRestore();
      Object.defineProperty(URL, "createObjectURL", {
        configurable: true,
        writable: true,
        value: originalCreateObjectURL,
      });
      Object.defineProperty(URL, "revokeObjectURL", {
        configurable: true,
        writable: true,
        value: originalRevokeObjectURL,
      });
    }
  });

  it("usePlatform falls back to navigator and refreshes from Tauri", async () => {
    invokeMock.mockResolvedValue({ family: "windows" });
    isTauriMock.mockReturnValue(true);

    const { result } = renderHook(() => usePlatform());
    expect(result.current).toMatch(/macos|linux|windows|other/);

    await waitFor(() => {
      expect(result.current).toBe("windows");
    });
  });

  it("usePlatform derives linux and other from navigator outside Tauri", () => {
    isTauriMock.mockReturnValue(false);
    const originalNavigator = Object.getOwnPropertyDescriptor(globalThis, "navigator");

    try {
      Object.defineProperty(globalThis, "navigator", {
        configurable: true,
        value: { userAgent: "X11; Linux x86_64" },
      });
      const linuxHook = renderHook(() => usePlatform());
      expect(linuxHook.result.current).toBe("linux");
      linuxHook.unmount();

      Object.defineProperty(globalThis, "navigator", {
        configurable: true,
        value: { userAgent: "Plan9" },
      });
      const otherHook = renderHook(() => usePlatform());
      expect(otherHook.result.current).toBe("other");
      otherHook.unmount();
    } finally {
      if (originalNavigator) {
        Object.defineProperty(globalThis, "navigator", originalNavigator);
      }
    }
  });

  it("usePlatform returns other when navigator is unavailable", () => {
    isTauriMock.mockReturnValue(false);
    const originalNavigator = Object.getOwnPropertyDescriptor(globalThis, "navigator");

    try {
      Object.defineProperty(globalThis, "navigator", {
        configurable: true,
        value: undefined,
      });
      const { result } = renderHook(() => usePlatform());
      expect(result.current).toBe("other");
    } finally {
      if (originalNavigator) {
        Object.defineProperty(globalThis, "navigator", originalNavigator);
      }
    }
  });
});
