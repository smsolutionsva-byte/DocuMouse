import type { DocumentSummary } from "@/lib/types";
import { isProcessing } from "@/lib/stages";
import { plural } from "@/lib/format";

/** One line of status, always dot + words (colour is never the only signal). */
export function StatusBadge({ doc }: { doc: DocumentSummary }) {
  let tone: "ok" | "attn" | "danger" | "busy" | "muted" = "muted";
  let text = "";
  if (doc.status === "failed") {
    tone = "danger";
    text = "Couldn't read";
  } else if (isProcessing(doc.status)) {
    tone = "busy";
    text = "Reading…";
  } else if (doc.approved) {
    tone = "ok";
    text = "Approved";
  } else if (doc.review_count > 0) {
    tone = "attn";
    text = `${plural(doc.review_count, "thing")} to check`;
  } else {
    tone = "ok";
    text = doc.edited_after_approval ? "Edited after approval" : "Looks good";
  }
  return <Status tone={tone}>{text}</Status>;
}

export function Status({
  tone,
  children,
  className = "",
}: {
  tone: "ok" | "attn" | "danger" | "busy" | "muted";
  children: React.ReactNode;
  className?: string;
}) {
  const dot = {
    ok: "bg-ok",
    attn: "bg-attn",
    danger: "bg-danger",
    busy: "bg-ink-3 animate-pulse",
    muted: "bg-ink-4",
  }[tone];
  const color = { ok: "text-ok", attn: "text-attn", danger: "text-danger", busy: "text-ink-2", muted: "text-ink-3" }[tone];
  return (
    <span className={`inline-flex items-center gap-1.5 text-[13px] font-medium ${color} ${className}`}>
      <span className={`size-1.5 rounded-full ${dot}`} aria-hidden />
      {children}
    </span>
  );
}
