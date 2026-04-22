import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Sidebar } from "@/components/Sidebar";
import { useUIStore } from "@/state/ui";

describe("Sidebar", () => {
  beforeEach(() => {
    useUIStore.setState({ activeSection: "repository" });
  });

  it("renders all nine navigation entries", () => {
    render(<Sidebar isMac={false} />);
    for (const label of [
      "Repository",
      "Memory Map",
      "Flow Graph",
      "Coverage & Gaps",
      "Generation",
      "Codegen Stream",
      "Dry Run / Inspect",
      "Audit Log",
      "Settings",
    ]) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }
  });

  it("updates the active section when an entry is clicked", () => {
    render(<Sidebar isMac={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    expect(useUIStore.getState().activeSection).toBe("settings");
  });
});
