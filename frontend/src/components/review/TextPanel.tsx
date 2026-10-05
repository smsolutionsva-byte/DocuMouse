"use client";

import { useEffect, useState } from "react";
import type { Source } from "@/lib/types";

interface Line {
  id: string;
  page: number;
  text: string;
  bbox: Source["bbox"];
  confidence: number;
}

/** Everything the document engine read, for documents without a known layout. */
export function TextPanel({ docId, onHover }: { docId: string; onHover: (s: Source | null) => void }) {
  const [lines, setLines] = useState<Line[] | null>(null);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (open && !lines) fetch(`/api/documents/${docId}/text`).then((r) => r.json()).then((d) => setLines(d.lines));
  }, [open, lines, docId]);

  return (
    <section className="px-3">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="text-2xs font-semibold uppercase tracking-[0.1em] text-ink-4 hover:text-ink-2"
      >
        {open ? "Hide" : "Show"} all text DocuMouse read
      </button>
      {open ? (
        <div className="mt-2 max-h-80 overflow-y-auto rounded-lg border border-line bg-surface p-2 quiet-scroll" onMouseLeave={() => onHover(null)}>
          {!lines ? (
            <div className="skeleton h-20" />
          ) : lines.length === 0 ? (
            <p className="p-2 text-sm text-ink-3">No text was found on this document.</p>
          ) : (
            lines.map((l) => (
              <p
                key={l.id}
                onMouseEnter={() => onHover({ page: l.page, bbox: l.bbox })}
                className={`rounded px-2 py-0.5 text-[13px] hover:bg-sunken ${l.confidence < 0.8 ? "text-attn" : "text-ink-2"}`}
                title={`Read with ${Math.round(l.confidence * 100)}% confidence`}
              >
                {l.text}
              </p>
            ))
          )}
        </div>
      ) : null}
    </section>
  );
}
