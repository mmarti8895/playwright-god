import { describe, expect, it, vi } from "vitest";
import { DEFAULT_SETTINGS } from "@/lib/settings";

vi.mock("@/lib/tauri", () => ({
  invokeCommand: vi.fn(),
  inTauri: vi.fn().mockReturnValue(false),
}));

describe("DEFAULT_SETTINGS retry fields", () => {
  it("includes llm_retry_max default of 3", () => {
    expect(DEFAULT_SETTINGS.llm_retry_max).toBe(3);
  });

  it("includes llm_retry_delay_s default of 2.0", () => {
    expect(DEFAULT_SETTINGS.llm_retry_delay_s).toBe(2.0);
  });

  it("llm_retry_max is a number", () => {
    expect(typeof DEFAULT_SETTINGS.llm_retry_max).toBe("number");
  });

  it("llm_retry_delay_s is a number", () => {
    expect(typeof DEFAULT_SETTINGS.llm_retry_delay_s).toBe("number");
  });
});
