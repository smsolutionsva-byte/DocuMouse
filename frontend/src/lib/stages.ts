import type { DocStatus } from "./types";

export const STAGES = [
  { key: "uploading", label: "Uploading", active: "Uploading…" },
  { key: "reading", label: "Reading", active: "Mouse is reading…" },
  { key: "understanding", label: "Understanding", active: "Figuring out what this is…" },
  { key: "extracting", label: "Extracting", active: "Picking out the details…" },
  { key: "checking", label: "Checking", active: "Double-checking the numbers…" },
  { key: "ready", label: "Ready for review", active: "Ready for review" },
] as const;

export function stageIndex(status: DocStatus | "uploading"): number {
  switch (status) {
    case "uploading":
      return 0;
    case "queued":
    case "reading":
      return 1;
    case "understanding":
      return 2;
    case "extracting":
      return 3;
    case "checking":
      return 4;
    case "ready":
      return 5;
    default:
      return -1;
  }
}

export const isProcessing = (s: DocStatus) => !["ready", "failed"].includes(s);
