"use client";

import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import { ArrowRight, Check, ChevronDown, Copy, FileText, Image as ImageIcon, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, uploadFile } from "@/lib/api";
import { fileSize, formatMoney, plural } from "@/lib/format";
import { STAGES, isProcessing, stageIndex } from "@/lib/stages";
import type { DocType, DocumentSummary } from "@/lib/types";
import { Button } from "../ui/Button";
import { Menu } from "../ui/Menu";
import { Mouse } from "../ui/Mouse";

const ACCEPT = ".pdf,.png,.jpg,.jpeg,.webp,.tif,.tiff,.bmp,application/pdf,image/*";
const MAX_PARALLEL = 3;

interface Item {
  key: string;
  file: File;
  docType: DocType | "auto"; // chosen when the file was added
  progress: number; // upload progress 0..1
  doc: DocumentSummary | null;
  error: string | null;
}

const TYPE_CHOICES: { value: DocType | "auto"; label: string }[] = [
  { value: "auto", label: "Auto-detect" },
  { value: "invoice", label: "Invoices" },
  { value: "receipt", label: "Receipts" },
];

export function Uploader({ onChange }: { onChange?: () => void }) {
  const [items, setItems] = useState<Item[]>([]);
  const [dragging, setDragging] = useState(false);
  const [docType, setDocType] = useState<DocType | "auto">("auto");
  const input = useRef<HTMLInputElement>(null);
  const depth = useRef(0);
  const queue = useRef<Item[]>([]);
  const active = useRef(0);

  const update = (key: string, patch: Partial<Item>) => setItems((all) => all.map((it) => (it.key === key ? { ...it, ...patch } : it)));

  // Upload a few files at a time; each finished upload starts the next one.
  const pump = useCallback(
    function next() {
      while (active.current < MAX_PARALLEL && queue.current.length) {
        const item = queue.current.shift()!;
        active.current++;
        uploadFile(item.file, item.docType, (p) => update(item.key, { progress: p }))
          .then((doc) => update(item.key, { doc, progress: 1 }))
          .catch((e) => update(item.key, { error: e instanceof ApiError ? e.message : "Upload failed." }))
          .finally(() => {
            active.current--;
            onChange?.();
            next();
          });
      }
    },
    [onChange],
  );

  const add = useCallback(
    (files: FileList | File[]) => {
      const list = Array.from(files);
      if (!list.length) return;
      const next: Item[] = list.map((file) => ({
        key: `${file.name}-${file.size}-${Math.random()}`,
        file,
        docType,
        progress: 0,
        doc: null,
        error: null,
      }));
      setItems((all) => [...next, ...all]);
      queue.current.push(...next);
      pump();
    },
    [pump, docType],
  );

  // The whole window is a drop target; the zone reacts so it's obvious where things go.
  useEffect(() => {
    const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes("Files");
    const enter = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth.current++;
      setDragging(true);
    };
    const over = (e: DragEvent) => hasFiles(e) && e.preventDefault();
    const leave = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      depth.current = Math.max(0, depth.current - 1);
      if (depth.current === 0) setDragging(false);
    };
    const drop = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth.current = 0;
      setDragging(false);
      if (e.dataTransfer?.files.length) add(e.dataTransfer.files);
    };
    window.addEventListener("dragenter", enter);
    window.addEventListener("dragover", over);
    window.addEventListener("dragleave", leave);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragenter", enter);
      window.removeEventListener("dragover", over);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("drop", drop);
    };
  }, [add]);

  // Follow each uploaded document through the pipeline.
  const pendingIds = items.filter((it) => it.doc && isProcessing(it.doc.status)).map((it) => it.doc!.id);
  useEffect(() => {
    if (!pendingIds.length) return;
    const t = setTimeout(async () => {
      const results = await Promise.allSettled(pendingIds.map((id) => api.get(id)));
      setItems((all) =>
        all.map((it) => {
          const r = results[pendingIds.indexOf(it.doc?.id ?? "")];
          return r && r.status === "fulfilled" ? { ...it, doc: r.value } : it;
        }),
      );
      if (results.some((r) => r.status === "fulfilled" && !isProcessing(r.value.status))) onChange?.();
    }, 800);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items]);

  const done = items.filter((it) => it.doc && !isProcessing(it.doc.status));
  const attention = done.reduce((n, it) => n + (it.doc!.review_count > 0 ? 1 : 0), 0);

  return (
    <div>
      <div
        className={`relative overflow-hidden rounded-[22px] border bg-surface transition-[border-color,box-shadow,transform] duration-300 ease-[var(--ease-out)] ${
          dragging ? "scale-[1.01] border-ink shadow-pop" : "border-line shadow-2"
        }`}
      >
        <div className="grid items-center gap-8 px-6 py-10 sm:px-12 sm:py-14 md:grid-cols-[minmax(0,1fr)_260px]">
          <div>
            <h1 className="font-display text-[44px] leading-[1.02] tracking-[-0.015em] sm:text-[60px]">
              {dragging ? (
                <>
                  Let go —<br />
                  <em className="text-ink-2">Mouse has it.</em>
                </>
              ) : (
                <>
                  Drop your
                  <br />
                  documents here.
                </>
              )}
            </h1>
            <p className="mt-4 max-w-md text-[15.5px] text-ink-3">
              Invoices, receipts, scans or phone photos. DocuMouse reads them, pulls out the details and checks the math — you just review.
            </p>
            <div className="mt-7 flex flex-wrap items-center gap-3">
              <Button variant="primary" size="lg" onClick={() => input.current?.click()}>
                Choose files
              </Button>
              <Menu
                label="Document type"
                trigger={(p) => (
                  <button {...p} className="inline-flex items-center gap-1 rounded-md px-2 py-1.5 text-[13.5px] text-ink-3 hover:text-ink">
                    {docType === "auto" ? "Type: auto-detect" : `Type: ${TYPE_CHOICES.find((c) => c.value === docType)?.label.toLowerCase()}`}
                    <ChevronDown className="size-3.5" />
                  </button>
                )}
                items={[
                  { heading: "These documents are" },
                  ...TYPE_CHOICES.map((c) => ({ label: `${c.value === docType ? "✓ " : ""}${c.label}`, onSelect: () => setDocType(c.value) })),
                ]}
              />
              <span className="hidden text-[12.5px] text-ink-4 sm:inline">PDF, JPG, PNG · up to 25 MB each</span>
            </div>
          </div>
          <PaperStack fanned={dragging} />
        </div>
        <input
          ref={input}
          type="file"
          multiple
          accept={ACCEPT}
          className="sr-only"
          aria-label="Choose documents to upload"
          onChange={(e) => {
            if (e.target.files) add(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      <AnimatePresence initial={false}>
        {items.length ? (
          <motion.section
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="mt-6"
            aria-label="Uploads"
            aria-live="polite"
          >
            <div className="mb-2 flex items-center justify-between px-1">
              <p className="text-[13.5px] text-ink-2">
                {done.length < items.length
                  ? `Reading ${plural(items.length - done.length, "document")}…`
                  : attention
                    ? `Found ${plural(items.length, "document")}. ${plural(attention, "needs", "need")} your attention.`
                    : `Found ${plural(items.length, "document")}. Everything looks good.`}
              </p>
              {done.length === items.length ? (
                <button onClick={() => setItems([])} className="text-[12.5px] text-ink-4 hover:text-ink-2">
                  Clear
                </button>
              ) : null}
            </div>
            <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
              <AnimatePresence initial={false}>
                {items.map((it) => (
                  <motion.li
                    key={it.key}
                    layout
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.22, ease: [0.2, 0.8, 0.2, 1] }}
                  >
                    <UploadRow item={it} onDismiss={() => setItems((all) => all.filter((x) => x.key !== it.key))} />
                  </motion.li>
                ))}
              </AnimatePresence>
            </ul>
          </motion.section>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

function UploadRow({ item, onDismiss }: { item: Item; onDismiss: () => void }) {
  const doc = item.doc;
  const status = item.error ? "failed" : doc ? doc.status : "uploading";
  const idx = stageIndex(status as never);
  const Icon = item.file.type.startsWith("image/") ? ImageIcon : FileText;
  const ready = doc?.status === "ready";

  return (
    <div className="flex items-center gap-4 px-4 py-3.5">
      <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-sunken text-ink-3">
        <Icon className="size-4" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="truncate text-[14.5px] font-medium">{ready && doc?.party ? doc.party : item.file.name}</span>
          <span className="shrink-0 text-[12px] text-ink-4">{ready && doc?.party ? item.file.name : fileSize(item.file.size)}</span>
        </div>
        {item.error || doc?.status === "failed" ? (
          <p className="text-[13px] text-danger">{item.error ?? doc?.error}</p>
        ) : ready ? (
          <p className="flex flex-wrap items-center gap-x-2 text-[13px] text-ink-3">
            <span className="capitalize">{doc!.doc_type === "unknown" ? "Other document" : doc!.doc_type}</span>
            {doc!.reference ? <span className="tabular">· {doc!.reference}</span> : null}
            {doc!.total ? <span className="tabular">· {formatMoney(doc!.total, doc!.currency)}</span> : null}
            {doc!.review_count ? (
              <span className="text-attn">· {plural(doc!.review_count, "thing")} to check</span>
            ) : (
              <span className="text-ok">· looks good</span>
            )}
            {doc!.duplicate_of.length ? (
              <span className="inline-flex items-center gap-1 text-attn">
                · <Copy className="size-3" /> possible duplicate
              </span>
            ) : null}
          </p>
        ) : (
          <div className="mt-1.5 flex items-center gap-3">
            <div className="flex flex-1 gap-1" aria-hidden>
              {STAGES.map((s, i) => (
                <span key={s.key} className="relative h-1 flex-1 overflow-hidden rounded-full bg-sunken">
                  <span
                    className="absolute inset-y-0 left-0 rounded-full bg-ink transition-[width] duration-500 ease-[var(--ease-out)]"
                    style={{ width: i < idx ? "100%" : i === idx ? (i === 0 ? `${Math.round(item.progress * 100)}%` : "45%") : "0%" }}
                  />
                </span>
              ))}
            </div>
            <span className="w-44 shrink-0 text-[12.5px] text-ink-3" role="status">
              {idx >= 0 ? STAGES[idx].active : ""}
            </span>
          </div>
        )}
      </div>
      {ready ? (
        <Link href={`/documents/${doc!.id}`} className="inline-flex shrink-0 items-center gap-1 rounded-md px-2.5 py-1.5 text-[13.5px] font-medium text-ink hover:bg-sunken">
          Review <ArrowRight className="size-3.5" />
        </Link>
      ) : doc?.status === "failed" || item.error ? (
        <button onClick={onDismiss} aria-label="Dismiss" className="grid size-8 place-items-center rounded-md text-ink-4 hover:bg-sunken hover:text-ink">
          <X className="size-4" />
        </button>
      ) : (
        <span className="size-8" />
      )}
      {ready ? <Check className="sr-only" aria-label="Ready" /> : null}
    </div>
  );
}

/** Three sheets of paper; they fan open when files are dragged over the window. */
function PaperStack({ fanned }: { fanned: boolean }) {
  const sheet = "absolute inset-0 rounded-[6px] border border-line bg-surface shadow-2 transition-transform duration-500 ease-[var(--ease-spring)]";
  return (
    <div className="relative mx-auto hidden aspect-[1/1.18] w-full max-w-[230px] md:block" aria-hidden>
      <div className={sheet} style={{ transform: fanned ? "rotate(-14deg) translate(-26px, 10px)" : "rotate(-5deg) translate(-6px, 6px)" }} />
      <div className={sheet} style={{ transform: fanned ? "rotate(11deg) translate(26px, 4px)" : "rotate(4deg) translate(6px, 2px)" }} />
      <div className={`${sheet} p-[12%]`} style={{ transform: fanned ? "translateY(-14px)" : "none" }}>
        <div className="h-2.5 w-1/2 rounded-full bg-sunken" />
        <div className="mt-2 h-2 w-1/3 rounded-full bg-sunken" />
        <div className="mt-[18%] space-y-2">
          <div className="h-2 w-full rounded-full bg-sunken" />
          <div className="h-2 w-5/6 rounded-full bg-sunken" />
          <div className="h-2 w-4/6 rounded-full bg-sunken" />
        </div>
        <div className="mt-[16%] ml-auto h-3 w-2/5 rounded-full bg-[color-mix(in_oklab,var(--cheese)_55%,var(--sunken))]" />
      </div>
      <div className="absolute -bottom-3 -right-4 transition-transform duration-500 ease-[var(--ease-spring)]" style={{ transform: fanned ? "translateY(-8px) rotate(-8deg)" : "none" }}>
        <Mouse className="size-14" mood={fanned ? "happy" : "idle"} />
      </div>
    </div>
  );
}
