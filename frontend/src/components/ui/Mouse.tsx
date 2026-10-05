/**
 * The DocuMouse mascot. Drawn with the same ink as the interface so it reads
 * as part of the product, not a sticker. Used sparingly.
 */
export function Mouse({
  className = "size-6",
  mood = "idle",
  title,
}: {
  className?: string;
  mood?: "idle" | "reading" | "happy";
  title?: string;
}) {
  const eyeY = mood === "reading" ? 14.6 : 13.6;
  return (
    <svg viewBox="0 0 32 32" className={className} role={title ? "img" : "presentation"} aria-hidden={title ? undefined : true}>
      {title ? <title>{title}</title> : null}
      <g stroke="var(--ink)" strokeWidth="1.6" strokeLinejoin="round">
        <circle cx="8.2" cy="9.4" r="5.6" fill="var(--surface)" />
        <circle cx="23.8" cy="9.4" r="5.6" fill="var(--surface)" />
        <path d="M5 17.4c0-5.6 4.9-9.6 11-9.6s11 4 11 9.6c0 5.2-4.6 9.4-11 9.4S5 22.6 5 17.4Z" fill="var(--surface)" />
      </g>
      <circle cx="8.2" cy="9.4" r="2.9" fill="var(--ear)" />
      <circle cx="23.8" cy="9.4" r="2.9" fill="var(--ear)" />
      {mood === "happy" ? (
        <g stroke="var(--ink)" strokeWidth="1.5" strokeLinecap="round" fill="none">
          <path d="M11.4 14.6c.6-.9 1.8-.9 2.4 0" />
          <path d="M18.2 14.6c.6-.9 1.8-.9 2.4 0" />
        </g>
      ) : (
        <g fill="var(--ink)">
          <circle cx="12.6" cy={eyeY} r="1.25" />
          <circle cx="19.4" cy={eyeY} r="1.25" />
        </g>
      )}
      <ellipse cx="16" cy="19.2" rx="1.7" ry="1.25" fill="var(--ear)" stroke="var(--ink)" strokeWidth="1.1" />
      <g stroke="var(--ink-3)" strokeWidth="0.9" strokeLinecap="round">
        <path d="M13 20.2 8.4 19.4M13 21.2l-4.4 1.2M19 20.2l4.6-.8M19 21.2l4.4 1.2" />
      </g>
    </svg>
  );
}
