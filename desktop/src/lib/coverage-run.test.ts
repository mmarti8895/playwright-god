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

import {
  runCoverage,
  cancelCoverage,
  readLatestSpecPath,
  type CoverageEvent,
} from "@/lib/coverage-run";

describe("coverage-run wrappers", () => {
  beforeEach(() => {
    invokeMock.mockReset();
    isTauriMock.mockReset();
    isTauriMock.mockReturnValue(true);
  });

  describe("runCoverage", () => {
    it("invokes run_coverage with repo and a Channel", async () => {
      invokeMock.mockResolvedValue(undefined);
      const handler = vi.fn();

      await runCoverage("/my/repo", handler);

      expect(invokeMock).toHaveBeenCalledWith(
        "run_coverage",
        expect.objectContaining({
          repo: "/my/repo",
          onEvent: expect.any(MockChannel),
        }),
      );
    });

    it("wires onmessage so events are forwarded to the callback", async () => {
      let capturedChannel: InstanceType<typeof MockChannel<CoverageEvent>> | null = null;
      invokeMock.mockImplementation((_cmd, args: Record<string, unknown>) => {
        capturedChannel = args["onEvent"] as InstanceType<typeof MockChannel<CoverageEvent>>;
        return Promise.resolve();
      });

      const events: CoverageEvent[] = [];
      await runCoverage("/repo", (e) => events.push(e));

      capturedChannel!.onmessage?.({ type: "run-started", spec_path: "/spec.ts" });
      capturedChannel!.onmessage?.({ type: "log-line", stream: "stdout", line: "ok" });
      capturedChannel!.onmessage?.({ type: "finished", exit_code: 0 });

      expect(events).toHaveLength(3);
      expect(events[0]).toMatchObject({ type: "run-started" });
      expect(events[2]).toMatchObject({ type: "finished", exit_code: 0 });
    });

    it("throws outside Tauri", async () => {
      isTauriMock.mockReturnValue(false);
      await expect(runCoverage("/repo", vi.fn())).rejects.toThrow(
        "runCoverage is only available inside Tauri.",
      );
    });
  });

  describe("cancelCoverage", () => {
    it("invokes cancel_coverage and returns the result", async () => {
      invokeMock.mockResolvedValue(true);
      await expect(cancelCoverage()).resolves.toBe(true);
      expect(invokeMock).toHaveBeenCalledWith("cancel_coverage", undefined);
    });

    it("returns false outside Tauri without calling invoke", async () => {
      isTauriMock.mockReturnValue(false);
      await expect(cancelCoverage()).resolves.toBe(false);
      expect(invokeMock).not.toHaveBeenCalled();
    });
  });

  describe("readLatestSpecPath", () => {
    it("returns the spec path from the backend", async () => {
      invokeMock.mockResolvedValue("/repo/.pg_runs/20260424T120000.000Z/generated.spec.ts");
      await expect(readLatestSpecPath("/repo")).resolves.toBe(
        "/repo/.pg_runs/20260424T120000.000Z/generated.spec.ts",
      );
      expect(invokeMock).toHaveBeenCalledWith("read_latest_spec_path", { repo: "/repo" });
    });

    it("returns null when no spec exists", async () => {
      invokeMock.mockResolvedValue(null);
      await expect(readLatestSpecPath("/repo")).resolves.toBeNull();
    });

    it("returns null outside Tauri", async () => {
      isTauriMock.mockReturnValue(false);
      await expect(readLatestSpecPath("/repo")).resolves.toBeNull();
      expect(invokeMock).not.toHaveBeenCalled();
    });
  });
});
