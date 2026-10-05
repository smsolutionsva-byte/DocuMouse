"use client";

import { AnimatePresence, motion } from "motion/react";
import { ArrowUp, LoaderCircle } from "lucide-react";
import { forwardRef, useImperativeHandle, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { AssistantReply } from "@/lib/types";
import { Button } from "../ui/Button";
import { Mouse } from "../ui/Mouse";
import { ChangePreview } from "./ChangePreview";
import { useReview } from "./context";

const EXAMPLES: Record<string, { simple: string[]; ai: string[] }> = {
  invoice: {
    simple: ["Change the vendor to Acme Technologies", "Delete blank rows"],
    ai: ["You merged quantity and price — separate them", "The invoice date should be October 4"],
  },
  receipt: {
    simple: ["Change the merchant to Corner Café", "Delete blank rows"],
    ai: ["The merchant name is wrong, it's Corner Café", "Remove the empty rows"],
  },
  unknown: {
    simple: ["Delete blank rows", "Rename column 1 to Item"],
    ai: ["Split this table at row 5", "Remove the empty rows"],
  },
};

export interface AssistantHandle {
  focus: () => void;
}

/**
 * AI proposes → DocuMouse previews → you approve → new version.
 * Nothing here writes to the document until "Approve".
 */
export const AssistantBar = forwardRef<AssistantHandle, { llmEnabled: boolean }>(function AssistantBar({ llmEnabled }, ref) {
  const { doc, commit } = useReview();
  const [message, setMessage] = useState("");
  const [thinking, setThinking] = useState(false);
  const [reply, setReply] = useState<AssistantReply | null>(null);
  const [asked, setAsked] = useState("");
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  useImperativeHandle(ref, () => ({ focus: () => input.current?.focus() }));

  const ask = async (text: string) => {
    const q = text.trim();
    if (!q || thinking) return;
    setThinking(true);
    setError(null);
    setReply(null);
    setAsked(q);
    try {
      setReply(await api.assistant(doc.id, q));
      setMessage("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setThinking(false);
    }
  };

  const approve = async () => {
    if (!reply?.operations.length) return;
    const ok = await commit(reply.operations, { author: "ai", message: reply.message });
    if (ok) setReply(null);
  };

  const currency = doc.data?.fields.currency?.value ?? null;
  const set = EXAMPLES[doc.data?.doc_type ?? "unknown"] ?? EXAMPLES.unknown;
  const examples = llmEnabled ? set.ai : set.simple;

  return (
    <div className="border-t border-line bg-surface/95 px-4 pb-4 pt-3 backdrop-blur sm:px-5">
      <AnimatePresence initial={false}>
        {(reply || thinking || error) && (
          <motion.div
            key="panel"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.24, ease: [0.2, 0.8, 0.2, 1] }}
            className="overflow-hidden"
          >
            <div className="quiet-scroll mb-3 max-h-[46vh] overflow-y-auto rounded-xl border border-line bg-surface-2 p-3.5" aria-live="polite">
              <p className="mb-2 text-[12.5px] text-ink-4">“{asked}”</p>
              <div className="flex gap-2.5">
                <Mouse className="mt-0.5 size-6 shrink-0" mood={thinking ? "reading" : reply?.operations.length ? "happy" : "idle"} />
                <div className="min-w-0 flex-1">
                  {thinking ? (
                    <p className="flex items-center gap-2 text-sm text-ink-3">
                      <LoaderCircle className="size-3.5 animate-spin" /> Thinking about it…
                    </p>
                  ) : error ? (
                    <p className="text-sm text-danger">{error}</p>
                  ) : reply ? (
                    <>
                      <p className="text-[14px] text-ink">{reply.reply}</p>
                      {reply.preview && reply.operations.length ? (
                        <div className="mt-3 rounded-lg border border-line bg-surface p-3">
                          <p className="mb-2.5 text-2xs font-semibold uppercase tracking-[0.08em] text-ink-4">Proposed change</p>
                          <ChangePreview preview={reply.preview} currency={currency} />
                        </div>
                      ) : null}
                    </>
                  ) : null}
                </div>
              </div>
              {reply?.operations.length ? (
                <div className="mt-3 flex justify-end gap-2">
                  <Button size="sm" variant="ghost" onClick={() => setReply(null)}>
                    Cancel
                  </Button>
                  <Button size="sm" variant="primary" onClick={approve} data-autofocus>
                    Approve
                  </Button>
                </div>
              ) : reply || error ? (
                <div className="mt-2 flex justify-end">
                  <Button size="sm" variant="ghost" onClick={() => (setReply(null), setError(null))}>
                    Dismiss
                  </Button>
                </div>
              ) : null}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(message);
        }}
        className="flex items-end gap-2 rounded-xl border border-line-strong bg-surface p-1.5 pl-3 shadow-1 transition-[border-color,box-shadow] focus-within:border-focus focus-within:shadow-[0_0_0_3px_color-mix(in_oklab,var(--focus)_14%,transparent)]"
      >
        <Mouse className="mb-1.5 size-5 shrink-0" />
        <label htmlFor="assistant-input" className="sr-only">
          Tell DocuMouse what to change
        </label>
        <textarea
          id="assistant-input"
          ref={input}
          rows={1}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              ask(message);
            }
          }}
          placeholder="Tell DocuMouse what to fix…"
          className="max-h-28 min-h-9 flex-1 resize-none bg-transparent py-2 text-[14.5px] leading-5 outline-none placeholder:text-ink-4"
        />
        <button
          type="submit"
          disabled={!message.trim() || thinking}
          aria-label="Send"
          className="grid size-8 shrink-0 place-items-center rounded-lg bg-ink text-surface transition hover:bg-[#33312c] disabled:bg-line disabled:text-ink-4"
        >
          {thinking ? <LoaderCircle className="size-4 animate-spin" /> : <ArrowUp className="size-4" />}
        </button>
      </form>
      {!reply && !thinking ? (
        <div className="mt-2 flex items-center gap-1.5">
          <div className="quiet-scroll flex min-w-0 flex-1 gap-1.5 overflow-x-auto">
            {examples.map((ex) => (
              <button
                key={ex}
                onClick={() => {
                  setMessage(ex);
                  input.current?.focus();
                }}
                className="shrink-0 rounded-md px-2 py-1 text-[12px] text-ink-3 hover:bg-sunken hover:text-ink"
              >
                {ex}
              </button>
            ))}
          </div>
          {!llmEnabled ? (
            <span
              className="hidden shrink-0 text-[11.5px] text-ink-4 xl:inline"
              title="Simple commands work without AI. Set DOCUMOUSE_LLM_PROVIDER to understand any request."
            >
              Simple commands
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
});
