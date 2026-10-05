"use client";

import { AnimatePresence, motion } from "motion/react";
import { createContext, useCallback, useContext, useRef, useState } from "react";

interface Toast {
  id: number;
  message: string;
  tone?: "default" | "error";
  action?: { label: string; onClick: () => void };
}

const ToastContext = createContext<(t: Omit<Toast, "id">) => void>(() => {});

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const next = useRef(1);

  const push = useCallback((t: Omit<Toast, "id">) => {
    const id = next.current++;
    setToasts((all) => [...all.slice(-2), { ...t, id }]);
    setTimeout(() => setToasts((all) => all.filter((x) => x.id !== id)), t.tone === "error" ? 6000 : 4200);
  }, []);

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-32 z-[60] flex flex-col items-center gap-2 px-4">
        <AnimatePresence initial={false}>
          {toasts.map((t) => (
            <motion.div
              key={t.id}
              layout
              initial={{ opacity: 0, y: 12, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 6, scale: 0.97 }}
              transition={{ duration: 0.2, ease: [0.2, 0.8, 0.2, 1] }}
              className={`pointer-events-auto flex items-center gap-4 rounded-lg px-4 py-2.5 text-sm shadow-pop ${
                t.tone === "error" ? "bg-danger text-white" : "bg-ink text-surface"
              }`}
            >
              <span>{t.message}</span>
              {t.action ? (
                <button
                  onClick={() => {
                    t.action?.onClick();
                    setToasts((all) => all.filter((x) => x.id !== t.id));
                  }}
                  className="-my-1 rounded-md px-2 py-1 font-medium text-cheese hover:bg-white/10"
                >
                  {t.action.label}
                </button>
              ) : null}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
