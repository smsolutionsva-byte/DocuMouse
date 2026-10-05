"use client";

import Link from "next/link";
import { Copy } from "lucide-react";
import type { DocType } from "@/lib/types";
import { Button } from "../ui/Button";
import { Mouse } from "../ui/Mouse";
import { useReview } from "./context";

export function Banners({ onChangeType, onKeepType }: { onChangeType: (t: DocType) => void; onKeepType: () => void }) {
  const { doc } = useReview();
  const c = doc.classification;
  const labels = doc.type_labels;
  const current = doc.data?.doc_type ?? "unknown";

  return (
    <div className="space-y-2.5 empty:hidden">
      {c?.mismatch ? (
        <Banner>
          <p className="font-medium text-ink">
            This looks more like {article(c.detected_label)} {c.detected_label.toLowerCase()} than {article(labels[current])} {labels[current].toLowerCase()}.
          </p>
          <p className="text-ink-3">
            DocuMouse is {Math.round(c.confidence * 100)}% sure
            {c.signals[c.detected_type]?.length ? ` — ${c.signals[c.detected_type].slice(0, 2).join(", ").toLowerCase()}` : ""}.
          </p>
          <div className="mt-2.5 flex flex-wrap gap-2">
            <Button size="sm" variant="primary" onClick={() => onChangeType(c.detected_type)}>
              Switch to {c.detected_label}
            </Button>
            <Button size="sm" variant="secondary" onClick={onKeepType}>
              Keep {labels[current]}
            </Button>
          </div>
        </Banner>
      ) : c?.uncertain ? (
        <Banner>
          <p className="font-medium text-ink">DocuMouse isn’t sure what this document is.</p>
          <p className="text-ink-3">Pick one and it’ll read the document again with that in mind.</p>
          <div className="mt-2.5 flex flex-wrap gap-2">
            {(["invoice", "receipt", "unknown"] as const).map((t) => (
              <Button
                key={t}
                size="sm"
                variant={t === current ? "primary" : "secondary"}
                onClick={() => (t === current ? onKeepType() : onChangeType(t))}
              >
                {t === "unknown" ? "Something else" : labels[t]}
              </Button>
            ))}
          </div>
        </Banner>
      ) : null}

      {doc.duplicate_of.length ? (
        <div className="flex gap-3 rounded-xl border border-attn-line bg-attn-soft px-4 py-3 text-[13.5px]">
          <Copy className="mt-0.5 size-4 shrink-0 text-attn" />
          <div className="min-w-0">
            <p className="font-medium text-attn">This document appears to be a duplicate.</p>
            <ul className="mt-0.5 text-ink-2">
              {doc.duplicate_of.slice(0, 3).map((d) => (
                <li key={d.id} className="truncate">
                  {d.reason} as{" "}
                  <Link href={`/documents/${d.id}`} className="underline decoration-attn-line underline-offset-2 hover:decoration-attn">
                    {d.filename}
                  </Link>
                </li>
              ))}
            </ul>
            <p className="mt-0.5 text-ink-3">Nothing was deleted — you decide what to keep.</p>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function Banner({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-3 rounded-xl border border-line bg-surface-2 px-4 py-3 text-[13.5px] animate-rise">
      <Mouse className="mt-0.5 size-6 shrink-0" />
      <div className="min-w-0">{children}</div>
    </div>
  );
}

function article(word: string) {
  return /^[aeiou]/i.test(word) ? "an" : "a";
}
