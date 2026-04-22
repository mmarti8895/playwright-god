import { invoke, isTauri } from "@tauri-apps/api/core";

export function inTauri(): boolean {
  return isTauri();
}

export async function invokeCommand<T>(
  command: string,
  args?: Record<string, unknown>,
): Promise<T> {
  if (!isTauri()) {
    throw new Error(`Tauri command unavailable: ${command}`);
  }
  return invoke<T>(command, args);
}

export function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  if (typeof error === "string" && error.trim()) return error;
  return String(error);
}
