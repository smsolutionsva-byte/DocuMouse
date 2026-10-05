"use client";

import { AnimatePresence, motion } from "motion/react";
import { RotateCcw, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import type { Preview, VersionInfo } from "@/lib/types";
import { Button } from "../ui/Button";
import { Mouse } from "../ui/Mouse";
import { ChangePreview } from "./ChangePreview";
import { useReview } from "./context";

const AUTHOR = { system: "DocuMouse", user: "You", ai: "AI, approved by you" } as const;

export function HistoryDrawer({ open, onClose, onRestored }: { open: boolean; onClose: () => void; onRestored: (v: VersionInfo) => void }) {
  const { doc } = useReview();
  const [versions, setVersions] = useState<VersionInfo[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  // Diffs are relative to the current version, so they're cached per (version, current).
  const [diffs, setDiffs] = useState<Record<string, Preview | null>>({});
  const diffKey = selected ? `${selected}:${doc.version?.id}` : null;
  const diff = diffKey ? diffs[diffKey] : null;

  useEffect(() => {
    if (!open) return;
    api.versions(doc.id).then((r) => setVersions(r.versions));
  }, [open, doc.id, doc.version?.id]);

  useEffect(() => {
    if (!selected || !diffKey) return;
    api.version(doc.id, selected).then((v) => setDiffs((d) => ({ ...d, [diffKey]: v.changes_from_current })));
  }, [selected, diffKey, doc.id]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const currency = doc.data?.fields.currency?.value ?? null;

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            className="fixed inset-0 z-40 bg-[rgb(27_26_23/0.18)]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.aside
            role="dialog"
            aria-label="Version history"
            className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col bg-surface shadow-pop"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ duration: 0.28, ease: [0.2, 0.8, 0.2, 1] }}
          >
            <div className="flex items-center justify-between border-b border-line px-5 py-4">
              <div>
                <h2 className="text-[17px] font-semibold">History</h2>
                <p className="text-[13px] text-ink-3">Every change is kept. The original file is never modified.</p>
              </div>
              <button onClick={onClose} aria-label="Close history" className="grid size-8 place-items-center rounded-md text-ink-3 hover:bg-sunken hover:text-ink">
                <X className="size-4" />
              </button>
            </div>
            <ol className="quiet-scroll flex-1 overflow-y-auto px-3 py-3">
              {!versions
                ? Array.from({ length: 4 }).map((_, i) => <li key={i} className="skeleton mx-2 my-3 h-12" />)
                : versions.map((v) => {
                    const isSel = selected === v.id;
                    return (
                      <li key={v.id} className="relative pl-6">
                        <span
                          aria-hidden
                          className={`absolute left-[11px] top-0 h-full w-px ${v.number === 1 ? "h-5" : ""} bg-line`}
                        />
                        <span
                          aria-hidden
                          className={`absolute left-[7px] top-[19px] size-[9px] rounded-full border-2 ${
                            v.head ? "border-ink bg-ink" : v.active ? "border-ink-3 bg-surface" : "border-line-strong bg-surface"
                          }`}
                        />
                        <button
                          onClick={() => setSelected(isSel || v.head ? null : v.id)}
                          aria-expanded={isSel}
                          className={`w-full rounded-lg px-3 py-2.5 text-left transition-colors ${isSel ? "bg-sunken" : "hover:bg-surface-2"} ${
                            v.active ? "" : "opacity-60"
                          }`}
                        >
                          <span className="flex items-baseline justify-between gap-3">
                            <span className="text-[14px] font-medium text-ink">
                              <span className="mr-1.5 text-ink-4 tabular">v{v.number}</span>
                              {v.message}
                            </span>
                            {v.head ? <span className="shrink-0 text-2xs font-semibold uppercase tracking-[0.08em] text-ok">Current</span> : null}
                            {!v.active ? <span className="shrink-0 text-2xs uppercase tracking-[0.08em] text-ink-4">Undone</span> : null}
                          </span>
                          <span className="mt-0.5 flex items-center gap-1.5 text-[12.5px] text-ink-3">
                            {v.author === "system" ? <Mouse className="size-3.5" /> : null}
                            {AUTHOR[v.author]} · {relativeTime(v.created_at)}
                          </span>
                        </button>
                        <AnimatePresence initial={false}>
                          {isSel && (
                            <motion.div
                              initial={{ opacity: 0, height: 0 }}
                              animate={{ opacity: 1, height: "auto" }}
                              exit={{ opacity: 0, height: 0 }}
                              className="overflow-hidden"
                            >
                              <div className="mx-3 mb-3 mt-1 rounded-lg border border-line p-3">
                                <p className="mb-2 text-2xs font-semibold uppercase tracking-[0.08em] text-ink-4">Restoring would change</p>
                                {diff ? (
                                  diff.fields.length || diff.tables.length ? (
                                    <ChangePreview preview={diff} currency={currency} />
                                  ) : (
                                    <p className="text-[13px] text-ink-3">Nothing — this matches the current version.</p>
                                  )
                                ) : (
                                  <div className="skeleton h-12" />
                                )}
                                <div className="mt-3 flex justify-end">
                                  <Button
                                    size="sm"
                                    variant="primary"
                                    onClick={async () => {
                                      await api.restore(doc.id, v.id);
                                      setSelected(null);
                                      onRestored(v);
                                    }}
                                  >
                                    <RotateCcw className="size-3.5" /> Restore v{v.number}
                                  </Button>
                                </div>
                              </div>
                            </motion.div>
                          )}
                        </AnimatePresence>
                      </li>
                    );
                  })}
              <li className="relative pl-6">
                <span aria-hidden className="absolute left-[7px] top-[19px] size-[9px] rounded-[2px] border-2 border-line-strong bg-surface" />
                <a href={doc.file_url} target="_blank" rel="noreferrer" className="block rounded-lg px-3 py-2.5 hover:bg-surface-2">
                  <span className="text-[14px] font-medium text-ink">Original upload</span>
                  <span className="block text-[12.5px] text-ink-3">{doc.filename} · always kept, open it</span>
                </a>
              </li>
            </ol>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
