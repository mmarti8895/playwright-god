import { Panel } from "@/components/Panel";

interface PlaceholderProps {
  title: string;
  description?: string;
}

export function Placeholder({ title, description }: PlaceholderProps) {
  return (
    <Panel className="flex h-full items-center justify-center">
      <div className="flex flex-col items-center gap-2 text-center">
        <div className="text-[15px] font-medium text-ink-700">{title}</div>
        {description && (
          <div className="max-w-md text-[13px] text-ink-500">{description}</div>
        )}
      </div>
    </Panel>
  );
}
