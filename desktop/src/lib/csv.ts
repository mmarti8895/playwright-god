import Papa from "papaparse";
import { save } from "@tauri-apps/plugin-dialog";
import { writeTextFile } from "@tauri-apps/plugin-fs";
import { inTauri } from "@/lib/tauri";

export interface CsvColumn<T> {
  header: string;
  value: (row: T) => unknown;
}

export interface ExportRowsResult {
  message: string;
}

export function formatOutputExportFilename(now: Date = new Date()): string {
  const stamp = now.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
  return `output_${stamp}.txt`;
}

function browserDownload(text: string, filename: string) {
  const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export async function exportRows<T>(
  rows: T[],
  columns: CsvColumn<T>[],
  filename: string,
): Promise<ExportRowsResult> {
  const data = rows.map((row) =>
    Object.fromEntries(columns.map((column) => [column.header, column.value(row)])),
  );
  const csv = Papa.unparse(data);

  if (!inTauri()) {
    browserDownload(csv, filename);
    return { message: `Downloaded ${filename}.` };
  }

  const path = await save({
    title: "Export CSV",
    defaultPath: filename,
  });
  if (!path) {
    return { message: "Export cancelled." };
  }

  await writeTextFile(path, csv);
  return { message: `Exported ${rows.length} rows to ${path}.` };
}

export async function exportOutputText(text: string): Promise<ExportRowsResult> {
  const filename = formatOutputExportFilename();

  if (!inTauri()) {
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    return { message: `Downloaded ${filename}.` };
  }

  const path = await save({
    title: "Export Output",
    defaultPath: filename,
  });
  if (!path) {
    return { message: "Export cancelled." };
  }

  await writeTextFile(path, text);
  return { message: `Exported output to ${path}.` };
}
