import { useUIStore, type SectionId } from "@/state/ui";
import { Repository } from "@/sections/Repository";
import { Placeholder } from "@/sections/Placeholder";
import { Settings } from "@/sections/Settings";
import { Generation } from "@/sections/Generation";
import { MemoryMapView } from "@/sections/MemoryMap";
import { FlowGraphView } from "@/sections/FlowGraph";
import { CoverageView } from "@/sections/Coverage";
import { RagView } from "@/sections/Rag";
import { AuditLog } from "@/sections/AuditLog";
import { CodegenStream } from "@/sections/CodegenStream";
import { Inspect } from "@/sections/Inspect";

const TITLES: Record<SectionId, string> = {
  repository: "Repository",
  "memory-map": "Memory Map",
  "flow-graph": "Flow Graph",
  coverage: "Coverage & Gaps",
  rag: "RAG Search",
  generation: "Generation",
  "codegen-stream": "Codegen Stream",
  inspect: "Dry Run / Inspect",
  "audit-log": "Audit Log",
  settings: "Settings",
};

export function MainPanel() {
  const active = useUIStore((s) => s.activeSection);
  const title = TITLES[active];

  let content;
  switch (active) {
    case "repository":
      content = <Repository />;
      break;
    case "generation":
      content = <Generation />;
      break;
    case "settings":
      content = <Settings />;
      break;
    case "memory-map":
      content = <MemoryMapView />;
      break;
    case "flow-graph":
      content = <FlowGraphView />;
      break;
    case "coverage":
      content = <CoverageView />;
      break;
    case "rag":
      content = <RagView />;
      break;
    case "audit-log":
      content = <AuditLog />;
      break;
    case "codegen-stream":
      content = <CodegenStream />;
      break;
    case "inspect":
      content = <Inspect />;
      break;
    default:
      content = (
        <Placeholder
          title={title}
          description="This view is part of the Phase-3 artifact viewers and will be wired up in a follow-up task batch."
        />
      );
  }

  return (
    <section className="flex flex-1 min-w-0 flex-col gap-4 overflow-y-auto p-6">
      <header className="flex items-baseline justify-between">
        <h1 className="text-[20px] font-semibold tracking-tight text-ink-900">
          {title}
        </h1>
      </header>
      <div className="flex-1 min-h-0">{content}</div>
    </section>
  );
}
