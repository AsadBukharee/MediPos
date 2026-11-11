"use client";

import { useEffect, useRef } from "react";

type Tone = "neutral" | "ok" | "warn" | "danger" | "brand";

const cx = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(" ");

export function Button({
  variant = "primary",
  size = "md",
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
}) {
  const variants = {
    primary: "bg-brand text-white hover:bg-brand-strong",
    secondary: "bg-surface text-ink border border-line hover:bg-canvas",
    ghost: "text-muted hover:bg-canvas hover:text-ink",
    danger: "bg-danger text-white hover:opacity-90",
  };
  const sizes = { sm: "h-8 px-2.5 text-[13px]", md: "h-9 px-3.5", lg: "h-12 px-5 text-base" };
  return (
    <button
      type="button"
      {...props}
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-md font-medium whitespace-nowrap transition-colors",
        "disabled:opacity-50 disabled:pointer-events-none",
        variants[variant],
        sizes[size],
        className,
      )}
    />
  );
}

// Callers may override width and height; the defaults only apply when they do not.
function fieldClass(className?: string) {
  const has = (prefix: string) => new RegExp(`(^|\\s)${prefix}-`).test(className ?? "");
  return cx(
    "rounded-md border border-line bg-surface px-2.5 text-ink placeholder:text-muted/70 disabled:bg-canvas",
    !has("h") && "h-9",
    !has("w") && "w-full",
    className,
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[13px] font-medium text-muted">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

export function Input({ className, ...props }: React.ComponentProps<"input">) {
  return <input {...props} className={fieldClass(className)} />;
}

export function Select({ className, ...props }: React.ComponentProps<"select">) {
  return <select {...props} className={cx(fieldClass(className), "pr-7")} />;
}

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div {...props} className={cx("rounded-lg border border-line bg-surface", className)} />;
}

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: React.ReactNode }) {
  const tones: Record<Tone, string> = {
    neutral: "bg-canvas text-muted",
    ok: "bg-ok-soft text-ok",
    warn: "bg-warn-soft text-warn",
    danger: "bg-danger-soft text-danger",
    brand: "bg-brand-soft text-brand-strong",
  };
  return (
    <span className={cx("inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium whitespace-nowrap", tones[tone])}>
      {children}
    </span>
  );
}

export const STATUS_TONES: Record<string, Tone> = {
  completed: "ok", confirmed: "ok", approved: "ok", received: "ok", fulfilled: "ok", active: "ok", ok: "ok", resolved: "ok",
  held: "warn", draft: "neutral", pending: "warn", low: "warn", ordered: "brand", partially_received: "brand",
  added: "brand", open: "warn", skipped: "neutral", low_stock: "warn",
  cancelled: "danger", rejected: "danger", out: "danger", blocked: "danger", out_of_stock: "danger", quarantined: "danger",
};

export function Status({ value }: { value: string }) {
  return <Badge tone={STATUS_TONES[value] ?? "neutral"}>{value.replace(/_/g, " ")}</Badge>;
}

export function PageHeader({ title, subtitle, children }: { title: string; subtitle?: string; children?: React.ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-0.5 text-muted">{subtitle}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  );
}

export function Notice({ tone = "danger", children }: { tone?: "danger" | "warn" | "ok"; children: React.ReactNode }) {
  if (!children) return null;
  const tones = { danger: "bg-danger-soft text-danger", warn: "bg-warn-soft text-warn", ok: "bg-ok-soft text-ok" };
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={cx("rounded-md px-3 py-2 text-[13px]", tones[tone])}>
      {children}
    </div>
  );
}

export function Tabs<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: [T, string][] }) {
  return (
    <div role="tablist" className="inline-flex rounded-md border border-line bg-surface p-0.5">
      {options.map(([key, label]) => (
        <button
          key={key}
          role="tab"
          aria-selected={value === key}
          onClick={() => onChange(key)}
          className={cx("h-8 rounded px-3 text-[13px] font-medium", value === key ? "bg-ink text-white" : "text-muted hover:text-ink")}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

export interface Column<T> {
  header: string;
  cell: (row: T) => React.ReactNode;
  align?: "right";
  className?: string;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  loading,
  error,
  empty = "Nothing here yet.",
  onRowClick,
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  loading?: boolean;
  error?: string | null;
  empty?: string;
  onRowClick?: (row: T) => void;
}) {
  return (
    <Card className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse text-left">
        <thead>
          <tr className="border-b border-line text-xs tracking-wide text-muted uppercase">
            {columns.map((column) => (
              <th key={column.header} className={cx("px-3 py-2.5 font-medium", column.align === "right" && "text-right")}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={cx("border-b border-line/70 last:border-0", onRowClick && "cursor-pointer hover:bg-canvas")}
            >
              {columns.map((column) => (
                <td key={column.header} className={cx("px-3 py-2.5 align-middle", column.align === "right" && "num text-right", column.className)}>
                  {column.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {error ? (
        <p className="px-3 py-8 text-center text-danger">{error}</p>
      ) : loading && rows.length === 0 ? (
        <p className="px-3 py-8 text-center text-muted">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="px-3 py-8 text-center text-muted">{empty}</p>
      ) : null}
    </Card>
  );
}

export function Modal({
  title,
  onClose,
  children,
  footer,
  wide,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(event) => event.target === ref.current && onClose()}
      className={cx(
        "m-auto w-[calc(100vw-2rem)] rounded-xl border border-line bg-surface p-0 text-ink shadow-xl backdrop:bg-ink/40",
        wide ? "max-w-4xl" : "max-w-lg",
      )}
    >
      <header className="no-print flex items-center justify-between border-b border-line px-5 py-3.5">
        <h2 className="text-base font-semibold">{title}</h2>
        <button onClick={onClose} aria-label="Close" className="rounded p-1 text-muted hover:bg-canvas">
          ✕
        </button>
      </header>
      <div className="max-h-[70vh] overflow-y-auto px-5 py-4">{children}</div>
      {footer && <footer className="no-print flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</footer>}
    </dialog>
  );
}

export function Stat({ label, value, tone, hint }: { label: string; value: React.ReactNode; tone?: Tone; hint?: string }) {
  const tones: Partial<Record<Tone, string>> = { warn: "text-warn", danger: "text-danger", ok: "text-ok" };
  return (
    <Card className="p-4">
      <p className="text-[13px] text-muted">{label}</p>
      <p className={cx("num mt-1 text-2xl font-semibold tracking-tight", tone && tones[tone])}>{value}</p>
      {hint && <p className="mt-0.5 text-xs text-muted">{hint}</p>}
    </Card>
  );
}
