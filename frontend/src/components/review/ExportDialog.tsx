"use client";

import { CheckCircle2, Download, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import { plural } from "@/lib/format";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { useReview } from "./context";

/** A short final review before export. Never blocks the export. */
export function ExportDialog({
  open,
  onClose,
  onReviewIssues,
  onDone,
}: {
  open: boolean;
  onClose: () => void;
  onReviewIssues: () => void;
  onDone: (approved: boolean) => void;
}) {
  const { doc } = useReview();
  const [layout, setLayout] = useState<"sections" | "line_items">("sections");
  const [working, setWorking] = useState(false);
  const v = doc.validation;
  if (!v) return null;
  const s = v.summary;
  const failedChecks = v.checks.filter((c) => c.status === "warn" || c.status === "fail");
  const clean = s.issues === 0 && failedChecks.length === 0;
  const lineItems = doc.data?.tables.find((t) => t.role === "line_items");

  const download = async (approve: boolean) => {
    setWorking(true);
    try {
      if (approve && !doc.approved) await api.approve(doc.id);
      const a = document.createElement("a");
      a.href = `/api/documents/${doc.id}/export.csv?layout=${layout}`;
      a.download = "";
      document.body.appendChild(a);
      a.click();
      a.remove();
      onDone(approve);
    } finally {
      setWorking(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} title={clean ? "Everything looks good" : "Almost there"} description="A quick look before you export.">
      <ul className="space-y-2 text-[14px]">
        <li className="flex items-center gap-2.5">
          <CheckCircle2 className="size-4 text-ok" />
          {plural(s.verified, "field")} verified
        </li>
        {s.tables ? (
          <li className="flex items-center gap-2.5">
            <CheckCircle2 className="size-4 text-ok" />
            {plural(s.tables, "table")} with {plural(doc.data?.tables.reduce((n, t) => n + t.rows.length, 0) ?? 0, "row")}
          </li>
        ) : null}
        {s.checks_passed ? (
          <li className="flex items-center gap-2.5">
            <CheckCircle2 className="size-4 text-ok" />
            {plural(s.checks_passed, "math check")} passed
          </li>
        ) : null}
        {s.needs_review ? (
          <li className="flex items-center gap-2.5 text-attn">
            <TriangleAlert className="size-4" />
            {plural(s.needs_review, "field")} {s.needs_review === 1 ? "needs" : "need"} review
          </li>
        ) : null}
        {s.flagged_rows ? (
          <li className="flex items-center gap-2.5 text-attn">
            <TriangleAlert className="size-4" />
            {plural(s.flagged_rows, "row")} {s.flagged_rows === 1 ? "doesn't" : "don't"} add up
          </li>
        ) : null}
        {failedChecks.map((c) => (
          <li key={c.id} className="flex items-center gap-2.5 text-attn">
            <TriangleAlert className="size-4" />
            {c.title}
          </li>
        ))}
      </ul>

      <fieldset className="mt-6">
        <legend className="mb-2 text-[13px] font-medium text-ink-2">CSV layout</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {(
            [
              ["sections", "Everything", "Details, then each table"],
              ["line_items", "Line items", lineItems ? "One row per item, ready for a spreadsheet" : "No line items found"],
            ] as const
          ).map(([value, title, hint]) => (
            <label
              key={value}
              className={`cursor-pointer rounded-lg border px-3 py-2.5 transition-colors ${
                layout === value ? "border-ink bg-surface-2" : "border-line hover:border-line-strong"
              } ${value === "line_items" && !lineItems ? "pointer-events-none opacity-50" : ""}`}
            >
              <input type="radio" name="layout" value={value} checked={layout === value} onChange={() => setLayout(value)} className="sr-only" />
              <span className="block text-[14px] font-medium">{title}</span>
              <span className="block text-[12.5px] text-ink-3">{hint}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        {clean ? (
          <>
            <Button variant="ghost" onClick={() => download(false)} disabled={working}>
              Just download
            </Button>
            <Button variant="primary" onClick={() => download(true)} disabled={working}>
              <Download className="size-4" /> Approve &amp; download CSV
            </Button>
          </>
        ) : (
          <>
            <Button variant="ghost" onClick={() => download(false)} disabled={working}>
              Export anyway
            </Button>
            <Button variant="primary" onClick={onReviewIssues}>
              Review issues
            </Button>
          </>
        )}
      </div>
    </Dialog>
  );
}
