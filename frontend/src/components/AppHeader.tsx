"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Mouse } from "./ui/Mouse";

export function AppHeader({ needsReview }: { needsReview?: number }) {
  const path = usePathname();
  const tab = (href: string, label: React.ReactNode, active: boolean) => (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={`relative rounded-md px-2.5 py-1.5 text-sm transition-colors ${
        active ? "text-ink" : "text-ink-3 hover:text-ink"
      }`}
    >
      {label}
      {active ? <span className="absolute inset-x-2.5 -bottom-[13px] h-[2px] rounded-full bg-ink" /> : null}
    </Link>
  );
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-paper/85 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-4 sm:px-6">
        <Link href="/" className="flex items-center gap-2 rounded-md" aria-label="DocuMouse home">
          <Mouse className="size-7" />
          <span className="text-[15px] font-semibold tracking-[-0.01em]">DocuMouse</span>
        </Link>
        <nav className="flex items-center gap-1" aria-label="Main">
          {tab("/", "Upload", path === "/")}
          {tab(
            "/documents",
            <span className="inline-flex items-center gap-1.5">
              Documents
              {needsReview ? (
                <span className="rounded-full bg-attn-soft px-1.5 text-2xs font-semibold leading-[18px] text-attn tabular">
                  {needsReview}
                </span>
              ) : null}
            </span>,
            path.startsWith("/documents"),
          )}
        </nav>
      </div>
    </header>
  );
}
