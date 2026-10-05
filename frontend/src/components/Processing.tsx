"use client";

import { Check } from "lucide-react";
import { STAGES, stageIndex } from "@/lib/stages";
import type { DocStatus } from "@/lib/types";
import { Mouse } from "./ui/Mouse";

/** Vertical list of the processing stages with the current one alive. */
export function StageList({ status }: { status: DocStatus | "uploading" }) {
  const current = stageIndex(status);
  return (
    <ol className="space-y-3" aria-label="Progress">
      {STAGES.map((stage, i) => {
        const done = i < current || status === "ready";
        const active = i === current && status !== "ready";
        return (
          <li key={stage.key} className="flex items-center gap-3" aria-current={active ? "step" : undefined}>
            <span
              className={`grid size-5 place-items-center rounded-full border transition-all duration-300 ${
                done ? "border-ink bg-ink text-surface" : active ? "border-ink" : "border-line-strong"
              }`}
            >
              {done ? <Check className="size-3" strokeWidth={3} /> : active ? <span className="size-1.5 animate-pulse rounded-full bg-ink" /> : null}
            </span>
            <span className={`text-[14.5px] transition-colors ${done ? "text-ink-3" : active ? "font-medium text-ink" : "text-ink-4"}`}>
              {active ? stage.active : stage.label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

/** A sheet of paper being read: the scan line communicates "reading" without words. */
export function ReadingPage({ className = "" }: { className?: string }) {
  return (
    <div className={`relative aspect-[1/1.32] w-full overflow-hidden rounded-[3px] bg-surface shadow-2 ring-1 ring-black/[0.04] ${className}`}>
      <div className="absolute inset-0 space-y-[6%] p-[10%]">
        <div className="skeleton h-[5%] w-1/2" />
        <div className="skeleton h-[2.5%] w-1/3" />
        <div className="grid grid-cols-2 gap-[6%] pt-[4%]">
          <div className="space-y-2">
            <div className="skeleton h-2.5 w-4/5" />
            <div className="skeleton h-2.5 w-3/5" />
          </div>
          <div className="space-y-2">
            <div className="skeleton h-2.5 w-full" />
            <div className="skeleton h-2.5 w-2/3" />
          </div>
        </div>
        <div className="space-y-2 pt-[6%]">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="skeleton h-2.5" style={{ width: `${92 - i * 7}%` }} />
          ))}
        </div>
      </div>
      <div
        aria-hidden
        className="absolute inset-x-0 top-0 h-[10%] animate-scan"
        style={{
          background: "linear-gradient(180deg, transparent, color-mix(in oklab, var(--cheese) 38%, transparent) 70%, color-mix(in oklab, var(--cheese) 80%, transparent))",
        }}
      />
      <Mouse className="absolute bottom-[5%] right-[6%] size-9" mood="reading" />
    </div>
  );
}
