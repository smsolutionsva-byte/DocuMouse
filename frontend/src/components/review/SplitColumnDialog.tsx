"use client";

import { Plus, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Column, Operation, Preview, TableData } from "@/lib/types";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { useReview } from "./context";

const SEPARATORS = [
  { label: "Spaces", value: null },
  { label: "Comma", value: "," },
  { label: "Slash", value: "/" },
  { label: "Dash", value: "-" },
] as const;

export function SplitColumnDialog({ table, column, onClose }: { table: TableData; column: Column | null; onClose: () => void }) {
  return (
    <Dialog
      open={!!column}
      onClose={onClose}
      title={`Split “${column?.name ?? ""}”`}
      description="DocuMouse cuts each cell at the separator. Nothing is thrown away: extra words stay together."
      width="max-w-xl"
    >
      {/* Keyed so each column starts with fresh suggestions. */}
      {column ? <SplitForm key={column.id} table={table} column={column} onClose={onClose} /> : null}
    </Dialog>
  );
}

function guessNames(name: string): string[] {
  const guess = name.split(/\s*(?:[/&+|,]|\band\b|\s)\s*/i).filter(Boolean);
  return guess.length >= 2 && guess.length <= 4 ? guess : [name, ""];
}

function SplitForm({ table, column, onClose }: { table: TableData; column: Column; onClose: () => void }) {
  const { doc, commit } = useReview();
  const [names, setNames] = useState<string[]>(() => guessNames(column.name));
  const [separator, setSeparator] = useState<string | null>(null);
  const [keepExtra, setKeepExtra] = useState<"first" | "last">("first");
  const [preview, setPreview] = useState<Preview["tables"][number]["after"]>(null);

  const finalNames = names.map((n, i) => n.trim() || `Part ${i + 1}`);
  const operation: Operation = {
    op: "split_column",
    table_id: table.id,
    column_id: column.id,
    new_columns: finalNames,
    separator,
    keep_extra: keepExtra,
  };

  // The preview comes from the backend so it shows exactly what will be applied.
  useEffect(() => {
    const t = setTimeout(() => {
      api
        .preview(doc.id, [operation])
        .then((r) => setPreview(r.changes.tables.find((x) => x.table_id === table.id)?.after ?? null))
        .catch(() => setPreview(null));
    }, 160);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(operation)]);

  const newIds = preview ? preview.columns.filter((c) => !table.columns.some((o) => o.id === c.id)).map((c) => c.id) : [];
  const sampleRows = preview?.rows.slice(0, 4) ?? [];

  return (
    <div className="space-y-5">
        <fieldset>
          <legend className="mb-2 text-[13px] font-medium text-ink-2">New columns</legend>
          <div className="flex flex-wrap items-center gap-2">
            {names.map((n, i) => (
              <div key={i} className="flex items-center rounded-md border border-line bg-surface focus-within:border-focus">
                <input
                  data-autofocus={i === 0 || undefined}
                  value={n}
                  placeholder={`Part ${i + 1}`}
                  aria-label={`Column ${i + 1} name`}
                  onChange={(e) => setNames((all) => all.map((x, j) => (j === i ? e.target.value : x)))}
                  className="h-9 w-32 bg-transparent px-2.5 text-sm outline-none"
                />
                {names.length > 2 ? (
                  <button
                    aria-label={`Remove column ${i + 1}`}
                    onClick={() => setNames((all) => all.filter((_, j) => j !== i))}
                    className="mr-1 grid size-6 place-items-center rounded text-ink-4 hover:bg-sunken hover:text-ink"
                  >
                    <X className="size-3.5" />
                  </button>
                ) : null}
              </div>
            ))}
            {names.length < 6 ? (
              <Button size="sm" variant="ghost" onClick={() => setNames((all) => [...all, ""])}>
                <Plus className="size-3.5" /> Add
              </Button>
            ) : null}
          </div>
        </fieldset>

        <div className="flex flex-wrap gap-x-8 gap-y-4">
          <fieldset>
            <legend className="mb-2 text-[13px] font-medium text-ink-2">Split at</legend>
            <div className="flex rounded-md bg-sunken p-0.5" role="radiogroup">
              {SEPARATORS.map((s) => (
                <button
                  key={s.label}
                  role="radio"
                  aria-checked={separator === s.value}
                  onClick={() => setSeparator(s.value)}
                  className={`h-8 rounded px-3 text-[13px] transition ${separator === s.value ? "bg-surface font-medium text-ink shadow-1" : "text-ink-3 hover:text-ink"}`}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </fieldset>
          <fieldset>
            <legend className="mb-2 text-[13px] font-medium text-ink-2">Extra words go to</legend>
            <div className="flex rounded-md bg-sunken p-0.5" role="radiogroup">
              {(["first", "last"] as const).map((k) => (
                <button
                  key={k}
                  role="radio"
                  aria-checked={keepExtra === k}
                  onClick={() => setKeepExtra(k)}
                  className={`h-8 rounded px-3 text-[13px] transition ${keepExtra === k ? "bg-surface font-medium text-ink shadow-1" : "text-ink-3 hover:text-ink"}`}
                >
                  {k === "first" ? "First column" : "Last column"}
                </button>
              ))}
            </div>
          </fieldset>
        </div>

        <div>
          <p className="mb-2 text-[13px] font-medium text-ink-2">Preview</p>
          <div className="overflow-x-auto rounded-lg border border-line">
            <table className="w-full text-[13px]">
              <thead className="bg-surface-2">
                <tr>
                  {preview?.columns.map((c) => (
                    <th key={c.id} className={`px-2.5 py-1.5 text-left font-semibold ${newIds.includes(c.id) ? "bg-[color-mix(in_oklab,var(--cheese)_30%,transparent)]" : "text-ink-3"}`}>
                      {c.name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sampleRows.map((r) => (
                  <tr key={r.id} className="border-t border-line">
                    {preview?.columns.map((c) => (
                      <td key={c.id} className={`px-2.5 py-1.5 ${newIds.includes(c.id) ? "bg-[color-mix(in_oklab,var(--cheese)_12%,transparent)]" : "text-ink-3"}`}>
                        {r.cells[c.id] || <span className="text-ink-4">—</span>}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            {!preview ? <div className="skeleton m-3 h-16" /> : null}
          </div>
        </div>

        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={async () => {
              if (await commit([operation])) onClose();
            }}
          >
            Split column
          </Button>
        </div>
    </div>
  );
}
