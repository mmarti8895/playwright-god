import { useEffect, useState } from "react";
import { invokeCommand, inTauri } from "@/lib/tauri";

export type PlatformFamily = "macos" | "linux" | "windows" | "other";

interface PlatformInfo {
  family: PlatformFamily;
}

function detectFromNavigator(): PlatformFamily {
  if (typeof navigator === "undefined") return "other";
  const ua = navigator.userAgent.toLowerCase();
  if (ua.includes("mac")) return "macos";
  if (ua.includes("win")) return "windows";
  if (ua.includes("linux")) return "linux";
  return "other";
}

export function usePlatform(): PlatformFamily {
  const [platform, setPlatform] = useState<PlatformFamily>(detectFromNavigator);

  useEffect(() => {
    if (!inTauri()) return;
    void invokeCommand<PlatformInfo>("platform_info").then((info) => {
      setPlatform(info.family);
    });
  }, []);

  return platform;
}
