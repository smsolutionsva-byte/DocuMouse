import type { DocumentData } from "./types";

/** Which fields, cells and columns differ between two versions (for the "just changed" glow). */
export function changedKeys(before: DocumentData | null, after: DocumentData | null): Set<string> {
  const out = new Set<string>();
  if (!before || !after) return out;
  for (const key of new Set([...Object.keys(before.fields), ...Object.keys(after.fields)])) {
    if ((before.fields[key]?.value ?? null) !== (after.fields[key]?.value ?? null)) out.add(`f:${key}`);
  }
  const old = new Map(before.tables.map((t) => [t.id, t]));
  for (const t of after.tables) {
    const b = old.get(t.id);
    const oldCols = new Set(b?.columns.map((c) => `${c.id}:${c.name}`) ?? []);
    for (const c of t.columns) if (!oldCols.has(`${c.id}:${c.name}`)) out.add(`col:${t.id}:${c.id}`);
    const oldRows = new Map(b?.rows.map((r) => [r.id, r]) ?? []);
    for (const r of t.rows) {
      const br = oldRows.get(r.id);
      for (const c of t.columns) {
        if ((br?.cells[c.id] ?? null) !== (r.cells[c.id] ?? null)) out.add(`c:${t.id}:${r.id}:${c.id}`);
      }
    }
  }
  return out;
}
