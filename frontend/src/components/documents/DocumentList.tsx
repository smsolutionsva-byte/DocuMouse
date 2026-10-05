"use client";

import Link from "next/link";
import { ChevronRight, Copy } from "lucide-react";
import { formatDate, formatMoney, relativeTime } from "@/lib/format";
import type { DocumentSummary } from "@/lib/types";
import { StatusBadge } from "../ui/StatusBadge";

const TYPE_LABEL = { invoice: "Invoice", receipt: "Receipt", unknown: "Other" } as const;

/** A calm, scannable list. Rows, not cards. */
export function DocumentList({ docs, compact = false }: { docs: DocumentSummary[]; compact?: boolean }) {
  return (
    <div className="overflow-hidden rounded-xl border border-line bg-surface">
      <div
        className={`hidden gap-x-4 border-b border-line bg-surface-2 px-4 py-2 text-2xs font-semibold uppercase tracking-[0.08em] text-ink-4 md:grid ${
          compact ? "md:grid-cols-[minmax(0,2fr)_100px_minmax(0,1fr)_150px_20px]" : "md:grid-cols-[minmax(0,2fr)_110px_110px_130px_150px_20px]"
        }`}
      >
        <span>Document</span>
        {compact ? <span>Type</span> : <span>Number</span>}
        {compact ? <span>Added</span> : <span>Date</span>}
        {compact ? null : <span className="text-right">Total</span>}
        <span>Status</span>
        <span />
      </div>
      <ul className="divide-y divide-line">
        {docs.map((d, i) => (
          <li key={d.id} className="animate-rise" style={{ animationDelay: `${Math.min(i, 10) * 25}ms` }}>
            <Link
              href={`/documents/${d.id}`}
              className={`group grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-0.5 px-4 py-3 transition-colors hover:bg-surface-2 focus-visible:bg-surface-2 md:gap-y-0 ${
                compact ? "md:grid-cols-[minmax(0,2fr)_100px_minmax(0,1fr)_150px_20px]" : "md:grid-cols-[minmax(0,2fr)_110px_110px_130px_150px_20px]"
              }`}
            >
              <span className="min-w-0">
                <span className="flex items-center gap-2">
                  <span className="truncate text-[14.5px] font-medium text-ink">{d.party || d.filename}</span>
                  {d.duplicate_of.length ? <Copy className="size-3.5 shrink-0 text-attn" aria-label="Possible duplicate" /> : null}
                </span>
                <span className="block truncate text-[12.5px] text-ink-4">
                  {d.party ? d.filename : d.doc_type ? TYPE_LABEL[d.doc_type] : "Waiting to be read"}
                  {!compact && d.doc_type ? <span className="md:hidden"> · {TYPE_LABEL[d.doc_type]}</span> : null}
                </span>
              </span>
              {compact ? (
                <span className="hidden text-[13.5px] text-ink-2 md:block">{d.doc_type ? TYPE_LABEL[d.doc_type] : "—"}</span>
              ) : (
                <span className="hidden truncate text-[13.5px] text-ink-2 tabular md:block">{d.reference ?? "—"}</span>
              )}
              {compact ? (
                <span className="hidden text-[13.5px] text-ink-3 md:block">{relativeTime(d.created_at)}</span>
              ) : (
                <span className="hidden text-[13.5px] text-ink-2 tabular md:block">{formatDate(d.doc_date) || "—"}</span>
              )}
              {compact ? null : (
                <span className="hidden text-right text-[14px] font-medium text-ink tabular md:block">{d.total ? formatMoney(d.total, d.currency) : "—"}</span>
              )}
              <span className="row-span-2 justify-self-end md:row-span-1 md:justify-self-start">
                <StatusBadge doc={d} />
              </span>
              <ChevronRight className="hidden size-4 text-ink-4 transition-transform group-hover:translate-x-0.5 group-hover:text-ink-3 md:block" />
              {!compact ? (
                <span className="text-[12.5px] text-ink-3 tabular md:hidden">
                  {[d.reference, formatDate(d.doc_date), d.total ? formatMoney(d.total, d.currency) : null].filter(Boolean).join(" · ")}
                </span>
              ) : null}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ListSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="overflow-hidden rounded-xl border border-line bg-surface" aria-busy="true">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 border-b border-line px-4 py-4 last:border-0">
          <div className="flex-1 space-y-1.5">
            <div className="skeleton h-3.5 w-48" />
            <div className="skeleton h-3 w-32" />
          </div>
          <div className="skeleton h-3.5 w-24" />
        </div>
      ))}
    </div>
  );
}
