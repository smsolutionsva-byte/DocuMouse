"use client";

import { createContext, useContext } from "react";
import type { DocumentDetail, Operation, Source } from "@/lib/types";

export type Focus =
  | { kind: "field"; key: string }
  | { kind: "row"; tableId: string; rowId: string }
  | { kind: "table"; tableId: string }
  | null;

export interface ReviewApi {
  doc: DocumentDetail;
  busy: boolean;
  /** Apply operations as a new version. Resolves to true on success. */
  commit: (ops: Operation[], opts?: { author?: "user" | "ai"; message?: string; quiet?: boolean }) => Promise<boolean>;
  focus: Focus;
  setFocus: (f: Focus) => void;
  /** Keys that just changed (for a brief highlight): "f:vendor", "c:t1:r2:c3", "col:t1:c3". */
  flash: Set<string>;
  sourceFor: (f: Focus) => Source | null;
}

export const ReviewContext = createContext<ReviewApi | null>(null);

export function useReview(): ReviewApi {
  const ctx = useContext(ReviewContext);
  if (!ctx) throw new Error("useReview must be used inside ReviewScreen");
  return ctx;
}
