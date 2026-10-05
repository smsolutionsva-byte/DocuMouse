"use client";

import Link from "next/link";
import { ArrowLeft, ChevronDown, History, Redo2, RefreshCw, Undo2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { changedKeys } from "@/lib/diff";
import { plural } from "@/lib/format";
import { isProcessing } from "@/lib/stages";
import type { DocType, DocumentDetail, Operation, Source } from "@/lib/types";
import { ReadingPage, StageList } from "../Processing";
import { Button, IconButton } from "../ui/Button";
import { Menu } from "../ui/Menu";
import { Mouse } from "../ui/Mouse";
import { Status } from "../ui/StatusBadge";
import { useToast } from "../ui/Toast";
import { AssistantBar, type AssistantHandle } from "./AssistantBar";
import { Banners } from "./Banners";
import { ReviewContext, useReview, type Focus, type ReviewApi } from "./context";
import { DocumentViewer } from "./DocumentViewer";
import { ExportDialog } from "./ExportDialog";
import { FieldsPanel } from "./FieldsPanel";
import { HistoryDrawer } from "./HistoryDrawer";
import { TableEditor } from "./TableEditor";
import { TextPanel } from "./TextPanel";

const UNDO_EVENT = "documouse:undo";
const REDO_EVENT = "documouse:redo";
const undoLatest = () => window.dispatchEvent(new Event(UNDO_EVENT));
const redoLatest = () => window.dispatchEvent(new Event(REDO_EVENT));

export function ReviewScreen({ id }: { id: string }) {
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [focus, setFocus] = useState<Focus>(null);
  const [hover, setHover] = useState<Source | null>(null);
  const [flash, setFlash] = useState<Set<string>>(new Set());
  const [historyOpen, setHistoryOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [pane, setPane] = useState<"document" | "details">("details");
  const [llmEnabled, setLlmEnabled] = useState(false);
  const [animateIn, setAnimateIn] = useState(false);
  const assistant = useRef<AssistantHandle>(null);
  const details = useRef<HTMLDivElement>(null);
  const toast = useToast();

  const receive = useCallback((d: DocumentDetail) => {
    setDoc(d);
    setError(null);
  }, []);

  const load = useCallback(
    () =>
      api
        .get(id)
        .then(receive)
        .catch((e) => setError(e instanceof ApiError ? e.message : "Couldn't load this document.")),
    [id, receive],
  );

  useEffect(() => {
    api
      .get(id)
      .then(receive)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Couldn't load this document."));
    api
      .health()
      .then((h) => setLlmEnabled(h.llm.enabled))
      .catch(() => {});
  }, [id, receive]);

  // Poll while the document is being read. If it finishes while you watch,
  // the results are revealed with a little choreography.
  useEffect(() => {
    if (!doc || !isProcessing(doc.status)) return;
    const t = setTimeout(() => {
      api
        .get(id)
        .then((d) => {
          if (d.status === "ready") {
            setAnimateIn(true);
            setTimeout(() => setAnimateIn(false), 1600);
          }
          receive(d);
        })
        .catch(() => {});
    }, 900);
    return () => clearTimeout(t);
  }, [doc, id, receive]);

  const replace = useCallback((next: DocumentDetail, before: DocumentDetail | null) => {
    setDoc(next);
    const keys = changedKeys(before?.data ?? null, next.data);
    if (keys.size) {
      setFlash(keys);
      setTimeout(() => setFlash(new Set()), 1500);
    }
  }, []);

  const commit = useCallback<ReviewApi["commit"]>(
    async (ops: Operation[], opts = {}) => {
      if (!doc) return false;
      setBusy(true);
      try {
        const next = await api.apply(doc.id, ops, { base: doc.version?.id, author: opts.author, message: opts.message });
        replace(next, doc);
        if (opts.author === "ai") {
          toast({ message: "Done.", action: { label: "Undo", onClick: undoLatest } });
        }
        return true;
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) {
          await load();
          toast({ message: "This document changed in another tab — showing the latest.", tone: "error" });
        } else {
          toast({ message: e instanceof ApiError ? e.message : "That change didn't save.", tone: "error" });
        }
        return false;
      } finally {
        setBusy(false);
      }
    },
    [doc, load, replace, toast],
  );

  const step = useCallback(
    async (dir: "undo" | "redo") => {
      if (!doc || busy) return;
      if (dir === "undo" ? !doc.can_undo : !doc.can_redo) return;
      setBusy(true);
      try {
        const label = doc.version?.message;
        const next = dir === "undo" ? await api.undo(doc.id) : await api.redo(doc.id);
        replace(next, doc);
        toast(
          dir === "undo"
            ? { message: `Undid “${label}”`, action: { label: "Redo", onClick: redoLatest } }
            : { message: `Redid “${next.version?.message}”` },
        );
      } catch (e) {
        toast({ message: e instanceof ApiError ? e.message : "Couldn't do that.", tone: "error" });
      } finally {
        setBusy(false);
      }
    },
    [doc, busy, replace, toast],
  );

  // ⌘Z / ⌘⇧Z outside text inputs (inside inputs the browser's own undo applies), "/" to talk to DocuMouse.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      const typing = t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z" && !typing) {
        e.preventDefault();
        step(e.shiftKey ? "redo" : "undo");
      } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "y" && !typing) {
        e.preventDefault();
        step("redo");
      } else if (e.key === "/" && !typing) {
        e.preventDefault();
        assistant.current?.focus();
      }
    };
    // Toast buttons ("Undo", "Redo") outlive the render that created them, so they signal via events.
    const onUndo = () => step("undo");
    const onRedo = () => step("redo");
    document.addEventListener("keydown", onKey);
    window.addEventListener(UNDO_EVENT, onUndo);
    window.addEventListener(REDO_EVENT, onRedo);
    return () => {
      document.removeEventListener("keydown", onKey);
      window.removeEventListener(UNDO_EVENT, onUndo);
      window.removeEventListener(REDO_EVENT, onRedo);
    };
  }, [step]);

  const sourceFor = useCallback(
    (f: Focus): Source | null => {
      if (!f || !doc?.data) return null;
      if (f.kind === "field") return doc.data.fields[f.key]?.source ?? null;
      const table = doc.data.tables.find((t) => t.id === f.tableId);
      if (f.kind === "row") return table?.rows.find((r) => r.id === f.rowId)?.source ?? table?.source ?? null;
      return table?.source ?? null;
    },
    [doc],
  );

  const changeType = useCallback(
    async (t: DocType) => {
      if (!doc) return;
      setBusy(true);
      try {
        const next = await api.setType(doc.id, t);
        replace(next, doc);
        toast({ message: `Read again as ${doc.type_labels[t].toLowerCase()}.`, action: { label: "Undo", onClick: undoLatest } });
      } catch (e) {
        toast({ message: e instanceof ApiError ? e.message : "Couldn't change the type.", tone: "error" });
      } finally {
        setBusy(false);
      }
    },
    [doc, replace, toast],
  );

  const reviewIssues = () => {
    setExportOpen(false);
    setPane("details");
    setTimeout(() => {
      const first = details.current?.querySelector<HTMLElement>("[data-attention] input, [data-attention] textarea");
      first?.focus();
      first?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 260);
  };

  const ctx = useMemo<ReviewApi | null>(
    () => (doc ? { doc, busy, commit, focus, setFocus, flash, sourceFor } : null),
    [doc, busy, commit, focus, flash, sourceFor],
  );

  if (error && !doc) return <FullMessage title="Couldn't open this document" body={error} />;
  if (!doc || !ctx) return <ReviewSkeleton />;
  if (doc.status === "failed") return <FailedState doc={doc} onRetry={async () => (await api.retry(doc.id), load())} />;
  if (isProcessing(doc.status) || !doc.data) return <ProcessingState doc={doc} />;

  const v = doc.validation!;
  const issues = v.summary.issues + v.checks.filter((c) => c.status === "warn" || c.status === "fail").length;
  const highlight = hover ?? sourceFor(focus);
  const otherTables = doc.data.tables.filter((t) => t.role !== "line_items");
  const lineItems = doc.data.tables.find((t) => t.role === "line_items");

  return (
    <ReviewContext.Provider value={ctx}>
      <div className="flex h-dvh flex-col">
        <header className="z-20 border-b border-line bg-surface">
          <div className="flex h-14 items-center gap-2 px-3 sm:gap-3 sm:px-4">
            <Link href="/documents" aria-label="Back to documents" className="grid size-9 place-items-center rounded-md text-ink-3 hover:bg-sunken hover:text-ink">
              <ArrowLeft className="size-4" />
            </Link>
            <div className="flex min-w-0 flex-1 items-center gap-2.5">
              <h1 className="truncate text-[15px] font-semibold tracking-[-0.01em]" title={doc.filename}>
                {doc.filename}
              </h1>
              <Menu
                label="Document type"
                trigger={(p) => (
                  <button {...p} className="inline-flex shrink-0 items-center gap-1 rounded-md border border-line px-2 py-0.5 text-[12.5px] text-ink-2 hover:border-line-strong hover:text-ink">
                    {doc.type_labels[doc.data!.doc_type]}
                    <ChevronDown className="size-3" />
                  </button>
                )}
                items={[
                  { heading: "Read this document as" },
                  ...(["invoice", "receipt", "unknown"] as const).map((t) => ({
                    label: `${t === doc.data!.doc_type ? "✓ " : ""}${doc.type_labels[t]}`,
                    onSelect: () => t !== doc.data!.doc_type && changeType(t),
                  })),
                ]}
              />
              <span className="hidden md:inline">
                {doc.approved ? (
                  <Status tone="ok">Approved</Status>
                ) : issues ? (
                  <Status tone="attn">{plural(issues, "thing")} to check</Status>
                ) : (
                  <Status tone="ok">Everything looks good</Status>
                )}
              </span>
            </div>
            <div className="flex items-center gap-0.5">
              <IconButton label="Undo (⌘Z)" onClick={() => step("undo")} disabled={!doc.can_undo || busy}>
                <Undo2 className="size-4" />
              </IconButton>
              <IconButton label="Redo (⌘⇧Z)" onClick={() => step("redo")} disabled={!doc.can_redo || busy}>
                <Redo2 className="size-4" />
              </IconButton>
              <IconButton label="History" onClick={() => setHistoryOpen(true)}>
                <History className="size-4" />
              </IconButton>
              <span className="mx-1.5 hidden h-5 w-px bg-line sm:block" />
              <Button variant="primary" size="sm" onClick={() => setExportOpen(true)} className="ml-1">
                Export
              </Button>
            </div>
          </div>
          <div className="flex border-t border-line lg:hidden" role="tablist" aria-label="View">
            {(["document", "details"] as const).map((p) => (
              <button
                key={p}
                role="tab"
                aria-selected={pane === p}
                onClick={() => setPane(p)}
                className={`flex-1 py-2 text-[13px] font-medium ${pane === p ? "text-ink shadow-[inset_0_-2px_0_var(--ink)]" : "text-ink-3"}`}
              >
                {p === "document" ? "Original" : `Details${issues ? ` · ${issues}` : ""}`}
              </button>
            ))}
          </div>
        </header>

        <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(0,1.05fr)_minmax(440px,0.95fr)]">
          <div className={`min-h-0 min-w-0 ${pane === "document" ? "flex" : "hidden"} flex-col lg:flex`}>
            <DocumentViewer pages={doc.pages} highlight={highlight} filename={doc.filename} />
          </div>
          <aside className={`min-h-0 min-w-0 flex-col border-line bg-surface lg:flex lg:border-l ${pane === "details" ? "flex" : "hidden"}`} aria-label="Extracted information">
            <div ref={details} className="quiet-scroll min-h-0 flex-1 overflow-y-auto">
              <div className="mx-auto max-w-[680px] space-y-7 px-3 py-5 sm:px-5">
                <Summary issues={issues} />
                <Banners onChangeType={changeType} onKeepType={async () => replace(await api.keepType(doc.id), doc)} />
                {doc.schema.length ? <FieldsPanel animateIn={animateIn} /> : null}
                {lineItems ? <TableEditor table={lineItems} animateIn={animateIn} /> : null}
                {!lineItems && doc.data.doc_type !== "unknown" ? <NoLineItems /> : null}
                {otherTables.length ? (
                  doc.data.doc_type === "unknown" ? (
                    otherTables.map((t) => <TableEditor key={t.id} table={t} />)
                  ) : (
                    <details className="group">
                      <summary className="cursor-pointer list-none px-3 text-2xs font-semibold uppercase tracking-[0.1em] text-ink-4 hover:text-ink-2">
                        {plural(otherTables.length, "other table")} found <span className="group-open:hidden">· show</span>
                      </summary>
                      <div className="mt-3 space-y-6">
                        {otherTables.map((t) => (
                          <TableEditor key={t.id} table={t} />
                        ))}
                      </div>
                    </details>
                  )
                ) : null}
                {doc.data.doc_type === "unknown" ? <TextPanel docId={doc.id} onHover={setHover} /> : null}
              </div>
            </div>
            <AssistantBar ref={assistant} llmEnabled={llmEnabled} />
          </aside>
        </div>
      </div>

      <HistoryDrawer
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        onRestored={async (v) => {
          const before = doc;
          const next = await api.get(doc.id);
          replace(next, before);
          setHistoryOpen(false);
          toast({ message: `Restored version ${v.number}.`, action: { label: "Undo", onClick: undoLatest } });
        }}
      />
      <ExportDialog
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        onReviewIssues={reviewIssues}
        onDone={async (approved) => {
          setExportOpen(false);
          if (approved) await load();
          toast({ message: approved ? "Approved. Your CSV is downloading." : "Your CSV is downloading." });
        }}
      />
    </ReviewContext.Provider>
  );
}

function Summary({ issues }: { issues: number }) {
  const { doc } = useReview();
  const v = doc.validation!;
  const party = doc.data?.fields.vendor?.value ?? doc.data?.fields.merchant?.value;
  return (
    <div className="flex items-start gap-3 px-3">
      <Mouse className="mt-0.5 size-7 shrink-0" mood={issues ? "idle" : "happy"} />
      <div>
        <p className="text-[15px] font-medium text-ink">
          {issues ? `${plural(issues, "thing")} ${issues === 1 ? "needs" : "need"} your attention.` : "Everything looks good."}
        </p>
        <p className="text-[13.5px] text-ink-3">
          {doc.type_labels[doc.data!.doc_type]}
          {party ? ` from ${party}` : ""} · {plural(v.summary.verified, "field")} verified
          {doc.pages.length > 1 ? ` · ${doc.pages.length} pages` : ""}
        </p>
      </div>
    </div>
  );
}

function NoLineItems() {
  const { commit } = useReview();
  return (
    <div className="mx-3 rounded-xl border border-dashed border-line-strong px-4 py-5 text-center">
      <p className="text-[14px] text-ink-2">DocuMouse didn’t find a line-item table.</p>
      <Button
        size="sm"
        variant="secondary"
        className="mt-3"
        onClick={() => commit([{ op: "add_table", title: "Line items", columns: ["Item", "Qty", "Price", "Amount"], line_items: true }])}
      >
        Add line items by hand
      </Button>
    </div>
  );
}

function ProcessingState({ doc }: { doc: DocumentDetail }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <MiniHeader title={doc.filename} />
      <div className="mx-auto grid w-full max-w-4xl flex-1 items-center gap-12 px-6 py-12 md:grid-cols-[minmax(0,320px)_1fr]">
        <ReadingPage className="mx-auto max-w-[300px]" />
        <div>
          <p className="mb-1 text-[13px] text-ink-3">{doc.filename}</p>
          <h1 className="mb-6 font-display text-[40px] leading-[1.05] tracking-[-0.01em]">Mouse is reading…</h1>
          <StageList status={doc.status} />
          <p className="mt-8 max-w-sm text-[13.5px] text-ink-3">You can leave this page — DocuMouse keeps working and the document will be waiting in your list.</p>
        </div>
      </div>
    </div>
  );
}

function FailedState({ doc, onRetry }: { doc: DocumentDetail; onRetry: () => void }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <MiniHeader title={doc.filename} />
      <div className="mx-auto flex max-w-lg flex-1 flex-col items-center justify-center px-6 text-center">
        <Mouse className="size-14" />
        <h1 className="mt-5 font-display text-[34px] leading-tight">{doc.error ?? "Mouse couldn’t read this one."}</h1>
        <p className="mt-2 text-[14.5px] text-ink-3">Your file is safe. You can try again, or open the original.</p>
        <div className="mt-6 flex gap-2">
          <Button variant="primary" onClick={onRetry}>
            <RefreshCw className="size-4" /> Try again
          </Button>
          <a href={doc.file_url} target="_blank" rel="noreferrer">
            <Button variant="secondary">Open original</Button>
          </a>
        </div>
        {doc.error_detail ? (
          <details className="mt-8 w-full text-left">
            <summary className="cursor-pointer text-[12.5px] text-ink-4 hover:text-ink-3">Technical details (for whoever runs DocuMouse)</summary>
            <pre className="mt-2 whitespace-pre-wrap rounded-lg bg-sunken p-3 text-[12px] text-ink-2">{doc.error_detail}</pre>
          </details>
        ) : null}
      </div>
    </div>
  );
}

function MiniHeader({ title }: { title: string }) {
  return (
    <header className="flex h-14 items-center gap-3 border-b border-line bg-surface px-4">
      <Link href="/" aria-label="Back" className="grid size-9 place-items-center rounded-md text-ink-3 hover:bg-sunken hover:text-ink">
        <ArrowLeft className="size-4" />
      </Link>
      <span className="truncate text-[15px] font-semibold">{title}</span>
    </header>
  );
}

function FullMessage({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-3 px-6 text-center">
      <Mouse className="size-12" />
      <h1 className="font-display text-3xl">{title}</h1>
      <p className="text-ink-3">{body}</p>
      <Link href="/documents" className="mt-2 text-sm underline underline-offset-2">
        Back to documents
      </Link>
    </div>
  );
}

function ReviewSkeleton() {
  return (
    <div className="flex h-dvh flex-col" aria-busy="true" aria-label="Loading">
      <div className="h-14 border-b border-line bg-surface" />
      <div className="grid flex-1 lg:grid-cols-[1.05fr_0.95fr]">
        <div className="bg-sunken p-8">
          <div className="skeleton mx-auto aspect-[1/1.3] max-w-[640px]" />
        </div>
        <div className="space-y-4 border-l border-line bg-surface p-8">
          {Array.from({ length: 7 }).map((_, i) => (
            <div key={i} className="grid grid-cols-[120px_1fr] gap-4">
              <div className="skeleton h-4" />
              <div className="skeleton h-9" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
