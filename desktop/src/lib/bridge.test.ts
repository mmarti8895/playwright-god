import { beforeEach, describe, expect, it, vi } from "vitest";

const { invokeMock, isTauriMock, MockChannel } = vi.hoisted(() => ({
  invokeMock: vi.fn(),
  isTauriMock: vi.fn(),
  MockChannel: class MockChannel<T> {
    onmessage?: (response: T) => void;
  },
}));

vi.mock("@tauri-apps/api/core", () => ({
  invoke: invokeMock,
  isTauri: isTauriMock,
  Channel: MockChannel,
}));

import { pickRepository } from "@/lib/commands";
import { readIndexStatus, ragSearch } from "@/lib/artifacts";
import { cancelPipeline, startPipeline } from "@/lib/pipeline";
import { errorMessage, invokeCommand } from "@/lib/tauri";

describe("desktop bridge wrappers", () => {
  beforeEach(() => {
    invokeMock.mockReset();
    isTauriMock.mockReset();
    isTauriMock.mockReturnValue(true);
  });

  it("pickRepository returns null outside Tauri", async () => {
    isTauriMock.mockReturnValue(false);
    await expect(pickRepository()).resolves.toBeNull();
    expect(invokeMock).not.toHaveBeenCalled();
  });

  it("startPipeline invokes run_pipeline with mode, description, and channel", async () => {
    invokeMock.mockResolvedValue("run-123");

    const runId = await startPipeline("/repo", vi.fn(), "full", "login flow");

    expect(runId).toBe("run-123");
    expect(invokeMock).toHaveBeenCalledWith(
      "run_pipeline",
      expect.objectContaining({
        repo: "/repo",
        mode: "full",
        description: "login flow",
        onEvent: expect.any(MockChannel),
      }),
    );
  });

  it("startPipeline and invokeCommand fail outside Tauri", async () => {
    isTauriMock.mockReturnValue(false);

    await expect(startPipeline("/repo", vi.fn())).rejects.toThrow(
      "Desktop pipeline commands are only available inside Tauri.",
    );
    await expect(invokeCommand("missing")).rejects.toThrow(
      "Tauri command unavailable: missing",
    );
  });

  it("cancelPipeline returns false outside Tauri and passes null when omitted", async () => {
    isTauriMock.mockReturnValue(false);
    await expect(cancelPipeline()).resolves.toBe(false);

    isTauriMock.mockReturnValue(true);
    invokeMock.mockResolvedValueOnce(true).mockResolvedValueOnce(false);

    await expect(cancelPipeline()).resolves.toBe(true);
    await expect(cancelPipeline("run-9")).resolves.toBe(false);

    expect(invokeMock).toHaveBeenNthCalledWith(1, "cancel_pipeline", { runId: null });
    expect(invokeMock).toHaveBeenNthCalledWith(2, "cancel_pipeline", { runId: "run-9" });
  });

  it("readIndexStatus forwards the backend payload", async () => {
    invokeMock.mockResolvedValue({
      has_index: true,
      has_memory_map: false,
      index_dir: "/repo/.idx",
      memory_map_path: null,
      active_run_id: null,
      active_run_mode: null,
    });

    await expect(readIndexStatus("/repo")).resolves.toEqual({
      has_index: true,
      has_memory_map: false,
      index_dir: "/repo/.idx",
      memory_map_path: null,
      active_run_id: null,
      active_run_mode: null,
    });
    expect(invokeMock).toHaveBeenCalledWith("read_index_status", { repo: "/repo" });
  });

  it("ragSearch normalizes backend errors into a result object", async () => {
    invokeMock.mockRejectedValue(new Error("missing index"));

    await expect(ragSearch("/repo", "login flow", 5)).resolves.toEqual({
      hits: [],
      error: "missing index",
    });
  });

  it("errorMessage handles Error, strings, and fallback values", () => {
    expect(errorMessage(new Error("boom"))).toBe("boom");
    expect(errorMessage("plain string")).toBe("plain string");
    expect(errorMessage({ detail: "x" })).toBe("[object Object]");
  });
});
