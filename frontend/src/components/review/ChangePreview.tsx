"use client";

import { ArrowRight } from "lucide-react";
import { formatDate, formatMoney } from "@/lib/format";
import type { Preview } from "@/lib/types";

const MAX_ROWS = 5;

/** Before → After, showing only what changes. */
export function ChangePreview({ preview, currency }: { preview: Preview; currency: string | null }) {
  const fmt = (kind: string, v: string | null) =>
    v == null || v === "" ? null : kind === "amount" ? formatMoney(v, currency) : kind === "date" ? formatDate(v) : v;

  return (
    <div className="space-y-3">
      {preview.fields.length ? (
        <ul className="space-y-1.5">
          {preview.fields.map((f) => (
            <li key={f.field} className="grid grid-cols-[96px_minmax(0,1fr)] items-baseline gap-3 text-[13.5px]">
              <span className="text-ink-3">{f.label}</span>
              <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5">
                <span className="text-ink-4 line-through decoration-ink-4/60">{fmt(f.kind, f.before) ?? "Not detected"}</span>
                <ArrowRight className="size-3.5 shrink-0 text-ink-4" aria-label="becomes" />
                <span className="rounded bg-[color-mix(in_oklab,var(--cheese)_35%,transparent)] px-1 font-medium text-ink">
                  {fmt(f.kind, f.after) ?? "Empty"}
                </span>
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      {preview.tables.map((t) => (
        <TableChange key={t.table_id} change={t} />
      ))}
    </div>
  );
}

function TableChange({ change }: { change: Preview["tables"][number] }) {
  const { before, after } = change;
  if (!after) return <p className="text-[13.5px] text-ink-2">Deletes the table “{before?.title}”.</p>;
  const oldCols = new Map(before?.columns.map((c) => [c.id, c]) ?? []);
  const newColIds = new Set(after.columns.filter((c) => oldCols.get(c.id)?.name !== c.name).map((c) => c.id));
  const removedCols = before?.columns.filter((c) => !after.columns.some((a) => a.id === c.id)) ?? [];
  const afterRowIds = new Set(after.rows.map((r) => r.id));
  const removedRows = before?.rows.filter((r) => !afterRowIds.has(r.id)) ?? [];
  const changedRows = new Set(change.changed_rows);

  const structural = newColIds.size > 0 || removedCols.length > 0;
  const rowsToShow = structural ? after.rows.slice(0, MAX_ROWS) : after.rows.filter((r) => changedRows.has(r.id)).slice(0, MAX_ROWS);

  return (
    <div className="space-y-2">
      {structural && before ? (
        <MiniTable label="Before" columns={before.columns} rows={before.rows.slice(0, MAX_ROWS)} mark={new Set(removedCols.map((c) => c.id))} tone="before" />
      ) : null}
      {removedRows.length ? (
        <MiniTable label={`Removes ${removedRows.length === 1 ? "this row" : `${removedRows.length} rows`}`} columns={before!.columns} rows={removedRows.slice(0, MAX_ROWS)} tone="removed" />
      ) : null}
      {rowsToShow.length ? (
        <MiniTable label={structural ? "After" : "Changes"} columns={after.columns} rows={rowsToShow} mark={newColIds} tone="after" />
      ) : null}
      {!rowsToShow.length && !removedRows.length && !structural ? (
        <p className="text-[13.5px] text-ink-2">Updates “{after.title}”.</p>
      ) : null}
    </div>
  );
}

function MiniTable({
  label,
  columns,
  rows,
  mark = new Set(),
  tone,
}: {
  label: string;
  columns: { id: string; name: string }[];
  rows: { id: string; cells: Record<string, string> }[];
  mark?: Set<string>;
  tone: "before" | "after" | "removed";
}) {
  const markBg =
    tone === "after" ? "bg-[color-mix(in_oklab,var(--cheese)_30%,transparent)]" : tone === "before" ? "bg-sunken line-through decoration-ink-4/60" : "";
  return (
    <div>
      <p className="mb-1 text-2xs font-semibold uppercase tracking-[0.08em] text-ink-4">{label}</p>
      <div className="quiet-scroll overflow-x-auto rounded-md border border-line">
        <table className={`w-full text-[12.5px] ${tone === "removed" ? "text-ink-4 line-through decoration-ink-4/50" : ""}`}>
          <thead className="bg-surface-2">
            <tr>
              {columns.map((c) => (
                <th key={c.id} className={`whitespace-nowrap px-2 py-1 text-left font-semibold ${mark.has(c.id) ? markBg : "text-ink-3"}`}>
                  {c.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-line">
                {columns.map((c) => (
                  <td key={c.id} className={`whitespace-nowrap px-2 py-1 ${mark.has(c.id) ? markBg : ""}`}>
                    {r.cells[c.id] || <span className="text-ink-4">—</span>}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
