"use client";

import { Check, CircleAlert, Sparkles } from "lucide-react";
import { useRef, useState } from "react";
import { currencySymbol, formatAmountInput, formatDate } from "@/lib/format";
import type { FieldSchema, FieldStatus, FieldValue } from "@/lib/types";
import { useReview } from "./context";

function display(kind: FieldSchema["kind"], value: string | null, currency: string | null): string {
  if (value == null) return "";
  if (kind === "amount") return formatAmountInput(value, currency);
  if (kind === "date") return formatDate(value);
  return value;
}

export function FieldRow({
  schema,
  field,
  status,
  reasons,
  index,
  animateIn,
}: {
  schema: FieldSchema;
  field: FieldValue | undefined;
  status: FieldStatus;
  reasons: string[];
  index: number;
  animateIn: boolean;
}) {
  const { doc, commit, setFocus, focus, flash } = useReview();
  const currency = doc.data?.fields.currency?.value ?? null;
  const value = field?.value ?? null;
  const shown = display(schema.kind, value, currency);
  // While typing, the draft wins; otherwise the field follows the document (undo, AI edits).
  const [typed, setTyped] = useState<string | null>(null);
  const draft = typed ?? shown;
  const input = useRef<HTMLInputElement & HTMLTextAreaElement>(null);

  const save = async () => {
    if (typed === null) return;
    const next = typed.trim();
    if (next === shown.trim()) return setTyped(null);
    await commit([{ op: "set_field", field: schema.key, value: next || null }]);
    setTyped(null);
  };

  const id = `field-${schema.key}`;
  const focused = focus?.kind === "field" && focus.key === schema.key;
  const needsAttention = status === "review" || status === "missing";
  const edited = field?.origin === "user" || field?.origin === "ai";
  const readTwice = !edited && status === "verified" && field?.second_opinion?.agrees;
  const isFlashing = flash.has(`f:${schema.key}`);
  const Tag = schema.kind === "multiline" ? "textarea" : "input";

  return (
    <div
      data-field={schema.key}
      data-attention={needsAttention || undefined}
      className={`group relative grid grid-cols-1 gap-x-4 gap-y-1 rounded-lg px-3 py-2 transition-colors sm:grid-cols-[132px_minmax(0,1fr)] ${
        focused ? "bg-surface-2" : ""
      } ${animateIn ? "animate-rise" : ""}`}
      style={animateIn ? { animationDelay: `${80 + index * 45}ms` } : undefined}
    >
      {needsAttention ? <span aria-hidden className="absolute bottom-2 left-0 top-2 w-[2px] rounded-full bg-attn" /> : null}
      <label htmlFor={id} className="pt-[7px] text-[13px] leading-5 text-ink-3">
        {schema.label}
        {edited ? <span className="ml-1.5 text-2xs text-ink-4">{field?.origin === "ai" ? "· AI edit" : "· edited"}</span> : null}
        {readTwice ? (
          <span className="ml-1.5 text-2xs text-ink-4" title={`${field?.second_opinion?.reader} read the same value`}>
            · read twice
          </span>
        ) : null}
      </label>
      <div className="min-w-0">
        <div
          className={`relative flex items-center rounded-md border bg-surface transition-[border-color,box-shadow] duration-150 focus-within:border-focus focus-within:shadow-[0_0_0_3px_color-mix(in_oklab,var(--focus)_14%,transparent)] ${
            needsAttention ? "border-attn-line" : "border-line hover:border-line-strong"
          } ${isFlashing ? "animate-flash" : ""}`}
        >
          {schema.kind === "amount" && currency ? (
            <span className="pl-2.5 text-sm text-ink-3 tabular" aria-hidden>
              {currencySymbol(currency).trim()}
            </span>
          ) : null}
          <Tag
            ref={input}
            id={id}
            value={draft}
            rows={schema.kind === "multiline" ? Math.min(4, Math.max(2, draft.split("\n").length)) : undefined}
            placeholder="Not detected"
            aria-invalid={needsAttention || undefined}
            aria-describedby={reasons.length ? `${id}-why` : undefined}
            onFocus={() => {
              setFocus({ kind: "field", key: schema.key });
            }}
            onChange={(e) => setTyped(e.target.value)}
            onBlur={save}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (schema.kind !== "multiline" || e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                (e.target as HTMLElement).blur();
              }
              if (e.key === "Escape") {
                setTyped(null);
                requestAnimationFrame(() => (e.target as HTMLElement).blur());
              }
            }}
            className={`min-w-0 flex-1 resize-none bg-transparent px-2.5 py-[7px] text-[14.5px] leading-5 outline-none placeholder:text-ink-4 ${
              schema.kind === "amount" ? "pl-1.5 tabular" : ""
            } ${schema.kind === "date" || schema.kind === "time" ? "tabular" : ""} ${
              status === "missing" ? "placeholder:text-attn/80" : ""
            } ${schema.kind === "amount" && !currency ? "pl-2.5" : ""}`}
          />
          <span className="pr-2.5" aria-hidden>
            {status === "verified" ? (
              <Check className="size-4 text-ok" strokeWidth={2.4} />
            ) : needsAttention ? (
              <CircleAlert className="size-4 text-attn" />
            ) : null}
          </span>
        </div>

        {reasons.length || field?.suggestion || (needsAttention && value) ? (
          <div id={`${id}-why`} className="mt-1.5 flex flex-wrap items-start gap-x-3 gap-y-1">
            {reasons.length ? (
              <p className="min-w-0 flex-1 text-[12.5px] leading-[18px] text-attn">{reasons[0]}</p>
            ) : null}
            {field?.suggestion ? (
              <button
                onClick={() => commit([{ op: "set_field", field: schema.key, value: field.suggestion!.value }])}
                className="inline-flex items-center gap-1 rounded-md bg-sunken px-2 py-0.5 text-[12.5px] text-ink-2 hover:bg-line"
                title={field.suggestion.reason}
              >
                <Sparkles className="size-3" />
                Use “{display(schema.kind, field.suggestion.value, currency)}”
              </button>
            ) : null}
            {status === "review" && value ? (
              <button
                onClick={() => commit([{ op: "confirm_field", field: schema.key }], { quiet: true })}
                className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[12.5px] font-medium text-ink-2 hover:bg-ok-soft hover:text-ok"
              >
                <Check className="size-3.5" />
                Looks right
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
