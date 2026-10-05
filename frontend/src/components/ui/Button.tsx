import { forwardRef, type ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "quiet" | "danger";
type Size = "sm" | "md" | "lg";

const base =
  "inline-flex items-center justify-center gap-2 font-medium whitespace-nowrap select-none " +
  "transition-[background-color,color,box-shadow,transform,opacity] duration-150 ease-[var(--ease-out)] " +
  "active:translate-y-px disabled:opacity-45 disabled:pointer-events-none";

const variants: Record<Variant, string> = {
  primary: "bg-ink text-surface hover:bg-[#33312c] shadow-1",
  secondary: "bg-surface text-ink border border-line-strong hover:border-ink-4 hover:bg-surface-2 shadow-1",
  ghost: "text-ink-2 hover:text-ink hover:bg-sunken",
  quiet: "text-ink-3 hover:text-ink",
  danger: "bg-danger text-white hover:brightness-110",
};

const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-[13px] rounded-md",
  md: "h-9 px-3.5 text-sm rounded-md",
  lg: "h-11 px-5 text-[15px] rounded-lg",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", className = "", type = "button", ...props },
  ref,
) {
  return <button ref={ref} type={type} className={`${base} ${variants[variant]} ${sizes[size]} ${className}`} {...props} />;
});

export const IconButton = forwardRef<HTMLButtonElement, ButtonProps & { label: string }>(function IconButton(
  { label, className = "", size = "md", variant = "ghost", ...props },
  ref,
) {
  const dim = size === "sm" ? "size-8" : size === "lg" ? "size-11" : "size-9";
  return (
    <Button
      ref={ref}
      aria-label={label}
      title={label}
      variant={variant}
      className={`${dim} !px-0 ${className}`}
      size={size}
      {...props}
    />
  );
});
