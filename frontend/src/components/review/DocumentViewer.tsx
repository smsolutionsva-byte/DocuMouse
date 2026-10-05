"use client";

import { Minus, Plus, Scan } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { PageInfo, Source } from "@/lib/types";

const ZOOMS = [0.5, 0.67, 0.8, 1, 1.25, 1.5, 2, 2.5];

/**
 * The original document, page by page, with a "highlighter" that glides to
 * wherever the selected value came from.
 */
export function DocumentViewer({ pages, highlight, filename }: { pages: PageInfo[]; highlight: Source | null; filename: string }) {
  const scroller = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState(1);
  const [loaded, setLoaded] = useState<Record<number, boolean>>({});

  // Bring the highlighted area into view, but only when it's off-screen.
  useEffect(() => {
    if (!highlight || !scroller.current) return;
    const el = scroller.current.querySelector<HTMLElement>(`[data-page="${highlight.page}"] [data-highlight]`);
    if (!el) return;
    const box = el.getBoundingClientRect();
    const view = scroller.current.getBoundingClientRect();
    const margin = 60;
    const offscreenY = box.top < view.top + margin || box.bottom > view.bottom - margin;
    const offscreenX = box.left < view.left || box.right > view.right;
    if (offscreenY || offscreenX) {
      el.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" });
    }
  }, [highlight]);

  const step = (dir: 1 | -1) =>
    setZoom((z) => {
      const i = ZOOMS.findIndex((v) => v >= z - 0.001);
      return ZOOMS[Math.min(ZOOMS.length - 1, Math.max(0, i + dir))];
    });

  return (
    <section aria-label={`Original document: ${filename}`} className="relative flex min-h-0 flex-col bg-sunken">
      <div
        ref={scroller}
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "+" || e.key === "=") step(1);
          if (e.key === "-") step(-1);
          if (e.key === "0") setZoom(1);
        }}
        className="quiet-scroll min-h-0 flex-1 overflow-auto outline-none focus-visible:outline-none"
      >
        <div className="mx-auto flex flex-col items-center gap-5 px-4 py-6 sm:px-8" style={{ width: `${Math.max(100, zoom * 100)}%` }}>
          {pages.map((page) => (
            <figure
              key={page.index}
              data-page={page.index}
              className="w-full"
              // Long till receipts would be enormous at full width; cap them by their aspect ratio.
              style={{ maxWidth: `${880 * zoom * Math.min(1, 1.55 / (page.height / page.width))}px` }}
            >
              <div
                className="relative w-full overflow-hidden rounded-[3px] bg-surface shadow-2 ring-1 ring-black/[0.04]"
                style={{ aspectRatio: `${page.width} / ${page.height}` }}
              >
                {!loaded[page.index] ? <div className="skeleton absolute inset-0 rounded-none" /> : null}
                {/* eslint-disable-next-line @next/next/no-img-element -- private, already-optimised page images */}
                <img
                  src={page.url}
                  alt={`Page ${page.index + 1} of ${filename}`}
                  draggable={false}
                  onLoad={() => setLoaded((l) => ({ ...l, [page.index]: true }))}
                  className={`absolute inset-0 size-full select-none transition-opacity duration-500 ${
                    loaded[page.index] ? "opacity-100" : "opacity-0"
                  }`}
                />
                <Highlighter source={highlight?.page === page.index ? highlight : null} />
              </div>
              {pages.length > 1 ? (
                <figcaption className="mt-2 text-center text-2xs text-ink-4 tabular">
                  Page {page.index + 1} of {pages.length}
                </figcaption>
              ) : null}
            </figure>
          ))}
        </div>
      </div>

      <div className="pointer-events-none absolute bottom-4 left-4 flex">
        <div className="pointer-events-auto flex items-center rounded-lg border border-line bg-surface/95 p-0.5 shadow-2 backdrop-blur">
          <button onClick={() => step(-1)} aria-label="Zoom out" className="grid size-8 place-items-center rounded-md text-ink-2 hover:bg-sunken">
            <Minus className="size-4" />
          </button>
          <button
            onClick={() => setZoom(1)}
            aria-label="Reset zoom"
            className="h-8 min-w-12 rounded-md px-1 text-xs font-medium text-ink-2 tabular hover:bg-sunken"
          >
            {Math.round(zoom * 100)}%
          </button>
          <button onClick={() => step(1)} aria-label="Zoom in" className="grid size-8 place-items-center rounded-md text-ink-2 hover:bg-sunken">
            <Plus className="size-4" />
          </button>
        </div>
      </div>
    </section>
  );
}

/** Keeps its last position while hidden so it can glide to the next one. */
function Highlighter({ source }: { source: Source | null }) {
  const [last, setLast] = useState<Source | null>(source);
  if (source && source !== last) setLast(source);
  const s = source ?? last;
  if (!s) return null;
  const pad = 0.004;
  const [x0, y0, x1, y1] = s.bbox;
  return (
    <div
      data-highlight
      aria-hidden
      className="pointer-events-none absolute rounded-[3px] transition-[left,top,width,height,opacity] duration-300 ease-[var(--ease-out)]"
      style={{
        left: `${(x0 - pad) * 100}%`,
        top: `${(y0 - pad * 1.4) * 100}%`,
        width: `${(x1 - x0 + pad * 2) * 100}%`,
        height: `${(y1 - y0 + pad * 2.8) * 100}%`,
        opacity: source ? 1 : 0,
        background: "color-mix(in oklab, var(--cheese) 55%, transparent)",
        mixBlendMode: "multiply",
        boxShadow: "0 0 0 2px color-mix(in oklab, var(--cheese) 85%, #c99a00), 0 0 0 7px color-mix(in oklab, var(--cheese) 22%, transparent)",
      }}
    />
  );
}

export function ViewerPlaceholder({ label }: { label: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 bg-sunken p-8 text-center text-sm text-ink-3">
      <Scan className="size-5" />
      {label}
    </div>
  );
}
