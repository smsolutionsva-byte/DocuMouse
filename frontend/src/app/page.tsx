"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { DocumentList, ListSkeleton } from "@/components/documents/DocumentList";
import { Uploader } from "@/components/upload/Uploader";
import { api } from "@/lib/api";
import { greeting, plural } from "@/lib/format";
import type { DocumentSummary } from "@/lib/types";

export default function Home() {
  const [recent, setRecent] = useState<DocumentSummary[] | null>(null);
  const [stats, setStats] = useState<{ needs_review: number; processed_today: number; total: number } | null>(null);
  const [offline, setOffline] = useState(false);

  const refresh = useCallback(() => {
    Promise.all([api.list({ limit: "8" }), api.stats()])
      .then(([l, s]) => {
        setRecent(l.documents);
        setStats(s);
        setOffline(false);
      })
      .catch(() => setOffline(true));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <>
      <AppHeader needsReview={stats?.needs_review} />
      <main className="mx-auto max-w-6xl px-4 pb-24 pt-8 sm:px-6 sm:pt-12">
        {/* The greeting depends on the visitor's clock, so it may differ from the server render. */}
        <p className="mb-4 h-5 px-1 text-[14px] text-ink-3" suppressHydrationWarning>
          {greeting()}.
        </p>
        <Uploader onChange={refresh} />

        {offline ? (
          <p className="mt-10 rounded-xl border border-danger/20 bg-danger-soft px-4 py-3 text-[14px] text-danger">
            DocuMouse can’t reach its server right now. Start the backend (see the README) and refresh.
          </p>
        ) : null}

        <section className="mt-14" aria-labelledby="recent-heading">
          <div className="mb-3 flex items-end justify-between gap-4 px-1">
            <div>
              <h2 id="recent-heading" className="text-[17px] font-semibold tracking-[-0.01em]">
                Recent documents
              </h2>
              {stats && stats.total ? (
                <p className="text-[13.5px] text-ink-3">
                  {stats.needs_review ? (
                    <Link href="/documents?status=needs_review" className="text-attn hover:underline">
                      {plural(stats.needs_review, "needs", "need")} review
                    </Link>
                  ) : (
                    "Nothing waiting for review"
                  )}
                  {" · "}
                  {stats.processed_today} processed today
                </p>
              ) : null}
            </div>
            {recent?.length ? (
              <Link href="/documents" className="inline-flex items-center gap-1 text-[13.5px] text-ink-3 hover:text-ink">
                All documents <ArrowRight className="size-3.5" />
              </Link>
            ) : null}
          </div>
          {recent === null ? (
            offline ? null : (
              <ListSkeleton />
            )
          ) : recent.length ? (
            <DocumentList docs={recent} compact />
          ) : (
            <div className="rounded-xl border border-dashed border-line-strong px-6 py-10 text-center">
              <p className="text-[14.5px] text-ink-2">Nothing here yet.</p>
              <p className="text-[13.5px] text-ink-3">Your documents will show up here once Mouse has read them.</p>
            </div>
          )}
        </section>
      </main>
    </>
  );
}
