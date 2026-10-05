"use client";

import {
  ArrowLeft,
  ArrowRight,
  Columns2,
  Combine,
  Ellipsis,
  Pencil,
  Plus,
  Rows2,
  Scissors,
  Sigma,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { useRef, useState } from "react";
import type { Column, Operation, TableData } from "@/lib/types";
import { Menu } from "../ui/Menu";
import { useReview } from "./context";
import { SplitColumnDialog } from "./SplitColumnDialog";

const NUMERIC_ROLES = new Set(["quantity", "unit_price", "tax", "amount", "tax_rate"]);
const ROLE_LABELS: Record<string, string> = {
  item: "Item name",
  description: "Description",
  quantity: "Quantity",
  unit_price: "Unit price",
  tax: "Tax",
  amount: "Line total",
};

export function TableEditor({ table, animateIn }: { table: TableData; animateIn?: boolean }) {
  const { doc, commit, setFocus, focus, flash } = useReview();
  const [splitting, setSplitting] = useState<Column | null>(null);
  const [renamingTable, setRenamingTable] = useState(false);
  const rowIssues = doc.validation?.rows[table.id] ?? {};
  const grid = useRef<HTMLTableElement>(null);
  const op = (o: Omit<Operation, "table_id"> & { op: string }) => ({ ...o, table_id: table.id }) as Operation;

  const moveFocus = (row: number, col: number) => {
    const el = grid.current?.querySelector<HTMLInputElement>(`[data-cell="${row}:${col}"]`);
    el?.focus();
    el?.select();
  };

  return (
    <section aria-label={table.title} className={animateIn ? "animate-rise" : ""} style={animateIn ? { animationDelay: "380ms" } : undefined}>
      <div className="mb-2 flex items-center justify-between gap-3 px-3">
        {renamingTable ? (
          <InlineName
            value={table.title}
            label="Table name"
            onDone={(name) => {
              setRenamingTable(false);
              if (name && name !== table.title) commit([op({ op: "rename_table", title: name })]);
            }}
          />
        ) : (
          <h3 className="text-2xs font-semibold uppercase tracking-[0.1em] text-ink-4">
            {table.title}
            <span className="ml-2 font-normal normal-case tracking-normal text-ink-4 tabular">
              {table.rows.length} {table.rows.length === 1 ? "row" : "rows"}
            </span>
          </h3>
        )}
        <Menu
          label={`${table.title} options`}
          align="right"
          trigger={(p) => (
            <button {...p} aria-label={`${table.title} options`} className="grid size-7 place-items-center rounded-md text-ink-3 hover:bg-sunken hover:text-ink">
              <Ellipsis className="size-4" />
            </button>
          )}
          items={[
            { label: "Rename table", icon: <Pencil className="size-3.5" />, onSelect: () => setRenamingTable(true) },
            { label: "Remove blank rows", icon: <Rows2 className="size-3.5" />, onSelect: () => commit([op({ op: "delete_blank_rows" })]) },
            "divider",
            { label: "Delete table", danger: true, icon: <Trash2 className="size-3.5" />, onSelect: () => commit([op({ op: "delete_table" })]) },
          ]}
        />
      </div>

      <div className="quiet-scroll overflow-x-auto rounded-lg border border-line bg-surface">
        <table ref={grid} className="w-full border-collapse text-[14px]">
          <thead>
            <tr className="border-b border-line bg-surface-2">
              <th scope="col" className="w-9 px-0" aria-label="Row number" />
              {table.columns.map((col, ci) => (
                <ColumnHeader
                  key={col.id}
                  table={table}
                  col={col}
                  index={ci}
                  flashing={flash.has(`col:${table.id}:${col.id}`)}
                  onSplit={() => setSplitting(col)}
                />
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, ri) => {
              const issues = rowIssues[row.id] ?? [];
              const focused = focus?.kind === "row" && focus.tableId === table.id && focus.rowId === row.id;
              return (
                <RowFragment key={row.id}>
                  <tr
                    data-row={row.id}
                    className={`group border-b border-line last:border-0 ${row.kind === "summary" ? "bg-surface-2 text-ink-3" : ""} ${
                      issues.length ? "bg-attn-soft/60" : ""
                    } ${focused ? "!bg-[color-mix(in_oklab,var(--cheese)_14%,var(--surface))]" : ""}`}
                    onFocus={() => setFocus({ kind: "row", tableId: table.id, rowId: row.id })}
                    onMouseEnter={() => row.source && setFocus({ kind: "row", tableId: table.id, rowId: row.id })}
                  >
                    <td className="relative w-9 px-0 text-center align-middle">
                      <span className="text-2xs text-ink-4 tabular group-hover:invisible group-focus-within:invisible">
                        {issues.length ? <TriangleAlert className="mx-auto size-3.5 text-attn" aria-label="This row needs a look" /> : ri + 1}
                      </span>
                      <div className="invisible absolute inset-0 grid place-items-center group-hover:visible group-focus-within:visible">
                        <Menu
                          label={`Row ${ri + 1} options`}
                          trigger={(p) => (
                            <button {...p} aria-label={`Row ${ri + 1} options`} className="grid size-6 place-items-center rounded text-ink-3 hover:bg-sunken hover:text-ink">
                              <Ellipsis className="size-3.5" />
                            </button>
                          )}
                          items={[
                            { label: "Insert row below", icon: <Plus className="size-3.5" />, onSelect: () => commit([op({ op: "add_row", after_row_id: row.id })]) },
                            {
                              label: "Merge with next row",
                              icon: <Combine className="size-3.5" />,
                              disabled: ri === table.rows.length - 1,
                              onSelect: () => commit([op({ op: "merge_rows", row_ids: [row.id, table.rows[ri + 1].id] })]),
                            },
                            {
                              label: row.kind === "summary" ? "This is an item, not a total" : "This is a total, not an item",
                              icon: <Sigma className="size-3.5" />,
                              onSelect: () => commit([op({ op: "set_row_kind", row_id: row.id, kind: row.kind === "summary" ? "item" : "summary" })]),
                            },
                            {
                              label: "Start a new table here",
                              icon: <Scissors className="size-3.5" />,
                              disabled: ri === 0,
                              onSelect: () => commit([op({ op: "split_table", before_row_id: row.id })]),
                            },
                            "divider",
                            { label: "Delete row", danger: true, icon: <Trash2 className="size-3.5" />, onSelect: () => commit([op({ op: "delete_rows", row_ids: [row.id] })]) },
                          ]}
                        />
                      </div>
                    </td>
                    {table.columns.map((col, ci) => (
                      <Cell
                        key={col.id}
                        value={row.cells[col.id] ?? ""}
                        wide={col.role === "item" || col.role === "description"}
                        numeric={NUMERIC_ROLES.has(col.role ?? "")}
                        summary={row.kind === "summary"}
                        flashing={flash.has(`c:${table.id}:${row.id}:${col.id}`)}
                        address={`${ri}:${ci}`}
                        label={`${col.name}, row ${ri + 1}`}
                        onCommit={(value) => commit([op({ op: "set_cell", row_id: row.id, column_id: col.id, value })])}
                        onNavigate={(dr, dc) => moveFocus(ri + dr, ci + dc)}
                      />
                    ))}
                  </tr>
                  {issues.length ? (
                    <tr className="border-b border-line bg-attn-soft/60">
                      <td />
                      <td colSpan={table.columns.length} className="px-2.5 pb-2 pt-0 text-[12.5px] text-attn">
                        {issues.join(" ")}
                      </td>
                    </tr>
                  ) : null}
                </RowFragment>
              );
            })}
          </tbody>
        </table>
        {table.rows.length === 0 ? <p className="px-4 py-6 text-center text-sm text-ink-3">No rows yet.</p> : null}
      </div>
      <button
        onClick={() => commit([op({ op: "add_row" })], { quiet: true })}
        className="mt-1.5 inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[13px] text-ink-3 hover:bg-sunken hover:text-ink"
      >
        <Plus className="size-3.5" /> Add row
      </button>

      <SplitColumnDialog table={table} column={splitting} onClose={() => setSplitting(null)} />
    </section>
  );
}

function RowFragment({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

function ColumnHeader({
  table,
  col,
  index,
  flashing,
  onSplit,
}: {
  table: TableData;
  col: Column;
  index: number;
  flashing: boolean;
  onSplit: () => void;
}) {
  const { commit } = useReview();
  const [renaming, setRenaming] = useState(false);
  const op = (o: Record<string, unknown> & { op: string }) => ({ ...o, table_id: table.id, column_id: col.id }) as Operation;
  const next = table.columns[index + 1];
  const numeric = NUMERIC_ROLES.has(col.role ?? "");

  return (
    <th scope="col" className={`group/col whitespace-nowrap px-0 text-left align-middle font-normal ${flashing ? "animate-flash" : ""}`}>
      <div className={`flex items-center gap-1 px-2.5 py-2 ${numeric ? "justify-end" : ""}`}>
        {renaming ? (
          <InlineName
            value={col.name}
            label="Column name"
            onDone={(name) => {
              setRenaming(false);
              if (name && name !== col.name) commit([op({ op: "rename_column", name })]);
            }}
          />
        ) : (
          <button
            onDoubleClick={() => setRenaming(true)}
            className="truncate text-[12.5px] font-semibold text-ink-2"
            title={`${col.name}${col.role ? ` · ${ROLE_LABELS[col.role] ?? col.role}` : ""} — double-click to rename`}
          >
            {col.name}
          </button>
        )}
        <Menu
          label={`${col.name} column options`}
          align={index > table.columns.length / 2 ? "right" : "left"}
          trigger={(p) => (
            <button
              {...p}
              aria-label={`${col.name} column options`}
              className="grid size-6 place-items-center rounded text-ink-4 opacity-0 transition-opacity hover:bg-sunken hover:text-ink focus:opacity-100 group-hover/col:opacity-100 aria-expanded:opacity-100"
            >
              <Ellipsis className="size-3.5" />
            </button>
          )}
          items={[
            { label: "Rename", icon: <Pencil className="size-3.5" />, onSelect: () => setRenaming(true) },
            { label: "Split into columns…", icon: <Scissors className="size-3.5" />, onSelect: onSplit },
            {
              label: next ? `Merge with “${next.name}”` : "Merge with next column",
              icon: <Combine className="size-3.5" />,
              disabled: !next,
              onSelect: () =>
                next &&
                commit([{ op: "merge_columns", table_id: table.id, column_ids: [col.id, next.id], name: `${col.name} ${next.name}` }]),
            },
            { label: "Insert column right", icon: <Columns2 className="size-3.5" />, onSelect: () => commit([{ op: "add_column", table_id: table.id, name: "New column", after_column_id: col.id }]) },
            "divider",
            { label: "Move left", icon: <ArrowLeft className="size-3.5" />, disabled: index === 0, onSelect: () => commit([op({ op: "move_column", to_index: index - 1 })]) },
            {
              label: "Move right",
              icon: <ArrowRight className="size-3.5" />,
              disabled: index === table.columns.length - 1,
              onSelect: () => commit([op({ op: "move_column", to_index: index + 1 })]),
            },
            ...(table.role === "line_items"
              ? ([
                  { heading: "This column holds" },
                  ...Object.entries(ROLE_LABELS).map(([role, label]) => ({
                    label: `${col.role === role ? "✓ " : ""}${label}`,
                    onSelect: () => commit([op({ op: "set_column_role", role: col.role === role ? null : role })]),
                  })),
                ] as const)
              : []),
            "divider",
            { label: "Delete column", danger: true, icon: <Trash2 className="size-3.5" />, disabled: table.columns.length < 2, onSelect: () => commit([op({ op: "delete_column" })]) },
          ]}
        />
      </div>
    </th>
  );
}

function Cell({
  value,
  wide,
  numeric,
  summary,
  flashing,
  address,
  label,
  onCommit,
  onNavigate,
}: {
  value: string;
  wide: boolean;
  numeric: boolean;
  summary: boolean;
  flashing: boolean;
  address: string;
  label: string;
  onCommit: (v: string) => void;
  onNavigate: (dr: number, dc: number) => void;
}) {
  const [typed, setTyped] = useState<string | null>(null);
  const draft = typed ?? value;

  return (
    <td className={`px-0 align-middle ${flashing ? "animate-flash" : ""}`}>
      <input
        data-cell={address}
        aria-label={label}
        value={draft}
        onChange={(e) => setTyped(e.target.value)}
        onBlur={() => {
          if (typed !== null && typed !== value) onCommit(typed);
          setTyped(null);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            onNavigate(e.shiftKey ? -1 : 1, 0);
          } else if (e.key === "Escape") {
            setTyped(null);
          } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault();
            onNavigate(e.key === "ArrowDown" ? 1 : -1, 0);
          }
        }}
        className={`w-full ${wide ? "min-w-[180px]" : "min-w-[84px]"} bg-transparent px-2.5 py-2 outline-none transition-shadow focus:bg-surface focus:shadow-[inset_0_0_0_2px_var(--focus)] ${
          numeric ? "text-right tabular" : ""
        } ${summary ? "italic" : ""}`}
      />
    </td>
  );
}

function InlineName({ value, label, onDone }: { value: string; label: string; onDone: (v: string) => void }) {
  const [v, setV] = useState(value);
  return (
    <input
      autoFocus
      aria-label={label}
      value={v}
      onChange={(e) => setV(e.target.value)}
      onFocus={(e) => e.target.select()}
      onBlur={() => onDone(v.trim())}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        if (e.key === "Escape") onDone(value);
      }}
      className="h-7 min-w-24 rounded border border-focus bg-surface px-1.5 text-[12.5px] font-semibold outline-none"
    />
  );
}
