"use client";

import Link from "next/link";
import { Download, Search, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { plural } from "@/lib/format";
import { isProcessing } from "@/lib/stages";
import type { DocumentSummary } from "@/lib/types";
import { AppHeader } from "../AppHeader";
import { Button } from "../ui/Button";
import { Mouse } from "../ui/Mouse";
import { DocumentList, ListSkeleton } from "./DocumentList";

const VIEWS = [
  { key: "all", label: "All" },
  { key: "needs_review", label: "Needs review" },
  { key: "invoice", label: "Invoices" },
  { key: "receipt", label: "Receipts" },
  { key: "approved", label: "Approved" },
] as const;
type View = (typeof VIEWS)[number]["key"];

export function Library({ initialStatus }: { initialStatus?: string }) {
  const [view, setView] = useState<View>(VIEWS.some((v) => v.key === initialStatus) ? (initialStatus as View) : "all");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [more, setMore] = useState(false);
  const [docs, setDocs] = useState<DocumentSummary[] | null>(null);
  const [needsReview, setNeedsReview] = useState(0);

  useEffect(() => {
    const t = setTimeout(() => setQuery(q.trim()), 220);
    return () => clearTimeout(t);
  }, [q]);

  const params = {
    q: query || undefined,
    type: view === "invoice" || view === "receipt" ? view : undefined,
    status: view === "needs_review" || view === "approved" ? view : undefined,
    date_from: from || undefined,
    date_to: to || undefined,
  };
  const key = JSON.stringify(params);

  useEffect(() => {
    let cancelled = false;
    const run = () =>
      api.list(params).then((r) => {
        if (cancelled) return;
        setDocs(r.documents);
        if (r.documents.some((d) => isProcessing(d.status))) timer = setTimeout(run, 1500);
      });
    let timer: ReturnType<typeof setTimeout> | undefined;
    run();
    api.stats().then((s) => !cancelled && setNeedsReview(s.needs_review));
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const filtered = Boolean(query || from || to || view !== "all");
  const exportHref = `/api/documents/export.csv${docs?.length && filtered ? `?ids=${docs.filter((d) => d.status === "ready").map((d) => d.id).join(",")}` : ""}`;

  return (
    <>
      <AppHeader needsReview={needsReview} />
      <main className="mx-auto max-w-6xl px-4 pb-24 pt-8 sm:px-6 sm:pt-10">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-display text-[40px] leading-none tracking-[-0.01em]">Documents</h1>
            <p className="mt-2 text-[14px] text-ink-3">
              {docs ? `${plural(docs.length, "document")}${filtered ? " match" : ""}` : " "}
            </p>
          </div>
          <a href={exportHref} download>
            <Button variant="secondary" size="sm" disabled={!docs?.length}>
              <Download className="size-3.5" /> Export {filtered ? "these" : "all"} as CSV
            </Button>
          </a>
        </div>

        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
          <label className="relative flex-1">
            <span className="sr-only">Search documents</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-4" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search vendors, invoice numbers, items, amounts…"
              className="h-10 w-full rounded-lg border border-line bg-surface pl-9 pr-9 text-[14.5px] outline-none transition placeholder:text-ink-4 focus:border-focus focus:shadow-[0_0_0_3px_color-mix(in_oklab,var(--focus)_14%,transparent)]"
            />
            {q ? (
              <button onClick={() => setQ("")} aria-label="Clear search" className="absolute right-2 top-1/2 grid size-6 -translate-y-1/2 place-items-center rounded text-ink-4 hover:text-ink">
                <X className="size-3.5" />
              </button>
            ) : null}
          </label>
          <Button variant={more ? "secondary" : "ghost"} size="sm" onClick={() => setMore((m) => !m)} aria-expanded={more}>
            <SlidersHorizontal className="size-3.5" /> Dates
          </Button>
        </div>

        {more ? (
          <div className="mb-4 flex flex-wrap items-center gap-3 animate-fade">
            <label className="flex items-center gap-2 text-[13.5px] text-ink-3">
              From
              <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="h-9 rounded-md border border-line bg-surface px-2 text-ink outline-none focus:border-focus" />
            </label>
            <label className="flex items-center gap-2 text-[13.5px] text-ink-3">
              to
              <input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="h-9 rounded-md border border-line bg-surface px-2 text-ink outline-none focus:border-focus" />
            </label>
            {from || to ? (
              <button onClick={() => (setFrom(""), setTo(""))} className="text-[13px] text-ink-3 hover:text-ink">
                Clear dates
              </button>
            ) : null}
          </div>
        ) : null}

        <nav className="mb-4 flex gap-1 overflow-x-auto quiet-scroll" aria-label="Filter documents">
          {VIEWS.map((v) => (
            <button
              key={v.key}
              onClick={() => setView(v.key)}
              aria-pressed={view === v.key}
              className={`shrink-0 rounded-md px-3 py-1.5 text-[13.5px] transition-colors ${
                view === v.key ? "bg-ink font-medium text-surface" : "text-ink-3 hover:bg-sunken hover:text-ink"
              }`}
            >
              {v.label}
              {v.key === "needs_review" && needsReview ? <span className="ml-1.5 tabular opacity-70">{needsReview}</span> : null}
            </button>
          ))}
        </nav>

        {docs === null ? (
          <ListSkeleton rows={6} />
        ) : docs.length ? (
          <DocumentList docs={docs} />
        ) : (
          <div className="flex flex-col items-center rounded-xl border border-dashed border-line-strong px-6 py-14 text-center">
            <Mouse className="size-10" />
            {filtered ? (
              <>
                <p className="mt-3 text-[15px] text-ink-2">Nothing matches that.</p>
                <p className="text-[13.5px] text-ink-3">Try a vendor name, an invoice number or an amount.</p>
              </>
            ) : (
              <>
                <p className="mt-3 text-[15px] text-ink-2">No documents yet.</p>
                <Link href="/" className="mt-1 text-[13.5px] text-ink underline underline-offset-2">
                  Drop some in
                </Link>
              </>
            )}
          </div>
        )}
      </main>
    </>
  );
}
