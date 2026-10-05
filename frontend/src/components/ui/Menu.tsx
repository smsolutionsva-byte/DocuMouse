"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useId, useRef, useState } from "react";

export interface MenuItem {
  label: string;
  onSelect: () => void;
  icon?: React.ReactNode;
  danger?: boolean;
  disabled?: boolean;
  hint?: string;
}

/** A small popover menu with arrow-key navigation. */
export function Menu({
  trigger,
  items,
  align = "left",
  label,
}: {
  trigger: (props: { onClick: () => void; "aria-expanded": boolean; "aria-haspopup": "menu"; "aria-controls": string }) => React.ReactNode;
  items: (MenuItem | "divider" | { heading: string })[];
  align?: "left" | "right";
  label: string;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const id = useId();

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    setTimeout(() => root.current?.querySelector<HTMLElement>('[role="menuitem"]:not([disabled])')?.focus(), 10);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const onMenuKey = (e: React.KeyboardEvent) => {
    if (!["ArrowDown", "ArrowUp"].includes(e.key)) return;
    e.preventDefault();
    const els = Array.from(root.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not([disabled])') ?? []);
    const i = els.indexOf(document.activeElement as HTMLElement);
    const next = e.key === "ArrowDown" ? els[(i + 1) % els.length] : els[(i - 1 + els.length) % els.length];
    next?.focus();
  };

  return (
    <div ref={root} className="relative inline-flex">
      {trigger({ onClick: () => setOpen((o) => !o), "aria-expanded": open, "aria-haspopup": "menu", "aria-controls": id })}
      <AnimatePresence>
        {open && (
          <motion.div
            id={id}
            role="menu"
            aria-label={label}
            onKeyDown={onMenuKey}
            initial={{ opacity: 0, y: -4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98 }}
            transition={{ duration: 0.14, ease: [0.2, 0.8, 0.2, 1] }}
            className={`absolute top-full z-40 mt-1.5 min-w-52 rounded-lg border border-line bg-surface p-1 shadow-pop ${
              align === "right" ? "right-0 origin-top-right" : "left-0 origin-top-left"
            }`}
          >
            {items.map((item, i) => {
              if (item === "divider") return <div key={i} className="my-1 h-px bg-line" />;
              if ("heading" in item)
                return (
                  <div key={i} className="px-2.5 pb-1 pt-2 text-2xs font-medium uppercase tracking-[0.08em] text-ink-4">
                    {item.heading}
                  </div>
                );
              return (
                <button
                  key={i}
                  role="menuitem"
                  disabled={item.disabled}
                  onClick={() => {
                    setOpen(false);
                    item.onSelect();
                  }}
                  className={`flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-[13.5px] outline-none disabled:opacity-40 ${
                    item.danger ? "text-danger hover:bg-danger-soft focus:bg-danger-soft" : "text-ink-2 hover:bg-sunken hover:text-ink focus:bg-sunken focus:text-ink"
                  }`}
                >
                  {item.icon ? <span className="grid size-4 place-items-center text-ink-3">{item.icon}</span> : null}
                  <span className="flex-1">{item.label}</span>
                  {item.hint ? <span className="text-2xs text-ink-4">{item.hint}</span> : null}
                </button>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
