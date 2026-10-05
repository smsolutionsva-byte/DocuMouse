"use client";

import { CheckCircle2, Info, TriangleAlert } from "lucide-react";
import { useState } from "react";
import type { Check, FieldSchema } from "@/lib/types";
import { useReview } from "./context";
import { FieldRow } from "./FieldRow";

export function FieldsPanel({ animateIn }: { animateIn: boolean }) {
  const { doc } = useReview();
  const [revealed, setRevealed] = useState<Set<string>>(new Set());
  const data = doc.data!;
  const validation = doc.validation!;

  const groups = new Map<string, FieldSchema[]>();
  for (const f of doc.schema) groups.set(f.group, [...(groups.get(f.group) ?? []), f]);

  let index = 0;
  return (
    <div className="space-y-6">
      {[...groups.entries()].map(([group, fields]) => {
        const visible = fields.filter((f) => validation.fields[f.key]?.status !== "empty" || revealed.has(f.key));
        const hidden = fields.filter((f) => !visible.includes(f));
        const checks = group === "Amounts" ? validation.checks : [];
        return (
          <section key={group} aria-labelledby={`group-${group}`}>
            <h3 id={`group-${group}`} className="mb-1 px-3 text-2xs font-semibold uppercase tracking-[0.1em] text-ink-4">
              {group}
            </h3>
            <div className="-mx-0">
              {visible.map((f) => (
                <FieldRow
                  key={f.key}
                  schema={f}
                  field={data.fields[f.key]}
                  status={validation.fields[f.key]?.status ?? "empty"}
                  reasons={validation.fields[f.key]?.reasons ?? []}
                  index={index++}
                  animateIn={animateIn}
                />
              ))}
            </div>
            {hidden.length ? (
              <p className="mt-1 px-3 text-[12.5px] text-ink-4">
                Not on this document:{" "}
                {hidden.map((f, i) => (
                  <span key={f.key}>
                    <button
                      onClick={() => setRevealed((s) => new Set(s).add(f.key))}
                      className="rounded text-ink-3 underline decoration-line-strong underline-offset-2 hover:text-ink hover:decoration-ink-3"
                      title={`Add ${f.label.toLowerCase()}`}
                    >
                      {f.label}
                    </button>
                    {i < hidden.length - 1 ? " · " : ""}
                  </span>
                ))}
              </p>
            ) : null}
            {checks.length ? <ChecksList checks={checks} /> : null}
          </section>
        );
      })}
    </div>
  );
}

export function ChecksList({ checks }: { checks: Check[] }) {
  const { setFocus } = useReview();
  return (
    <ul className="mt-3 space-y-1.5 px-3" aria-label="Arithmetic checks">
      {checks.map((c) => {
        const Icon = c.status === "pass" ? CheckCircle2 : c.status === "info" ? Info : TriangleAlert;
        const color = c.status === "pass" ? "text-ok" : c.status === "info" ? "text-ink-4" : "text-attn";
        return (
          <li
            key={c.id}
            className={`flex gap-2.5 rounded-lg px-3 py-2 text-[13px] ${c.status === "warn" || c.status === "fail" ? "bg-attn-soft" : "bg-surface-2"}`}
            onMouseEnter={() => c.fields[0] && setFocus({ kind: "field", key: c.fields[0] })}
          >
            <Icon className={`mt-[2px] size-4 shrink-0 ${color}`} />
            <div className="min-w-0">
              <p className={`font-medium ${c.status === "pass" ? "text-ink" : c.status === "info" ? "text-ink-3" : "text-attn"}`}>{c.title}</p>
              {c.detail ? <p className="text-ink-3 tabular">{c.detail}</p> : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
