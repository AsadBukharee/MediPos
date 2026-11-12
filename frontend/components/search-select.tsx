"use client";

import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Card, Input } from "@/components/ui";

const PANEL_HEIGHT = 320;

export interface SelectOption {
  value: string;
  label: string;
  /** Second line: a phone number, a code, an account number — whatever tells two alike apart. */
  hint?: string;
  disabled?: boolean;
}

/**
 * A select you can type into. Same job as a native <select>, but it filters as you type, which
 * is the difference between usable and unusable once a list runs past a dozen entries.
 */
export function SearchSelect({
  value,
  onChange,
  options,
  placeholder = "Choose…",
  emptyLabel,
  emptyHint,
  disabled,
  loading,
  label,
  className = "w-56",
  onOpenChange,
  footer,
}: {
  value: string;
  onChange: (value: string, option?: SelectOption) => void;
  options: SelectOption[];
  placeholder?: string;
  /** Label for the "nothing selected" entry. Without it, the value cannot be cleared. */
  emptyLabel?: string;
  emptyHint?: string;
  disabled?: boolean;
  loading?: boolean;
  label: string;
  className?: string;
  /** Told when the panel opens, so options can be fetched only when someone looks. */
  onOpenChange?: (open: boolean) => void;
  /** Rendered under the list — somewhere to put "add a new one". */
  footer?: (close: () => void) => React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [term, setTerm] = useState("");
  const [active, setActive] = useState(0);
  const [anchor, setAnchor] = useState<{ left: number; width: number; top: number | null; bottom: number | null } | null>(null);
  const listId = useId();
  const wrapper = useRef<HTMLDivElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLUListElement>(null);

  const all = useMemo<SelectOption[]>(
    () => (emptyLabel ? [{ value: "", label: emptyLabel, hint: emptyHint }, ...options] : options),
    [emptyLabel, emptyHint, options],
  );
  const needle = term.trim().toLowerCase();
  const shown = needle
    ? all.filter((option) => `${option.label} ${option.hint ?? ""}`.toLowerCase().includes(needle))
    : all;
  const chosen = all.find((option) => option.value === value);

  /** Where the panel should sit, in viewport coordinates. */
  const place = () => {
    const box = wrapper.current?.getBoundingClientRect();
    if (!box) return;
    const room = window.innerHeight - box.bottom;
    const above = room < PANEL_HEIGHT && box.top > room;
    setAnchor({
      left: Math.min(box.left, window.innerWidth - Math.max(box.width, 280) - 8),
      width: Math.max(box.width, 280),
      top: above ? null : box.bottom + 4,
      bottom: above ? window.innerHeight - box.top + 4 : null,
    });
  };

  const openPanel = () => {
    place();
    setOpen(true);
    setActive(Math.max(0, all.findIndex((option) => option.value === value)));
    onOpenChange?.(true);
  };

  const close = () => {
    setOpen(false);
    setTerm("");
    onOpenChange?.(false);
  };

  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!wrapper.current?.contains(target) && !panel.current?.contains(target)) {
        setOpen(false);
        setTerm("");
      }
    };
    // The panel is fixed to the viewport, so follow the trigger when anything moves.
    const follow = () => place();
    document.addEventListener("pointerdown", outside);
    window.addEventListener("resize", follow);
    window.addEventListener("scroll", follow, true);
    return () => {
      document.removeEventListener("pointerdown", outside);
      window.removeEventListener("resize", follow);
      window.removeEventListener("scroll", follow, true);
    };
  }, [open]);

  useLayoutEffect(() => {
    if (open && shown.length) list.current?.children[active]?.scrollIntoView({ block: "nearest" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, open]);

  const pick = (option: SelectOption) => {
    if (option.disabled) return;
    onChange(option.value, option);
    close();
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Escape") return close();
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((current) => Math.min(Math.max(current + step, 0), Math.max(shown.length - 1, 0)));
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (shown[active]) pick(shown[active]);
    }
  };

  return (
    <div ref={wrapper} className={`relative ${className}`}>
      <button
        type="button"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-haspopup="listbox"
        aria-label={label}
        disabled={disabled}
        onClick={() => (open ? close() : openPanel())}
        onKeyDown={(event) => {
          if (!open && (event.key === "ArrowDown" || event.key === "Enter")) {
            event.preventDefault();
            openPanel();
          }
        }}
        className="flex h-9 w-full items-center justify-between gap-2 rounded-md border border-line bg-surface px-2.5 text-left text-ink disabled:bg-canvas disabled:opacity-60"
      >
        <span className={`truncate ${chosen ? "" : "text-muted"}`}>{chosen?.label ?? placeholder}</span>
        <span aria-hidden className="shrink-0 text-muted">▾</span>
      </button>

      {open && anchor && createPortal(
        <Card
          ref={panel}
          style={{
            position: "fixed",
            left: anchor.left,
            width: anchor.width,
            ...(anchor.top !== null ? { top: anchor.top } : { bottom: anchor.bottom ?? 0 }),
          }}
          className="z-50 overflow-hidden p-0 shadow-xl"
        >
          <div className="border-b border-line p-2">
            <Input
              autoFocus
              value={term}
              onChange={(event) => (setTerm(event.target.value), setActive(0))}
              onKeyDown={onKeyDown}
              placeholder="Type to search"
              aria-label={`Search ${label.toLowerCase()}`}
              className="h-8"
            />
          </div>
          <ul id={listId} ref={list} role="listbox" aria-label={label} className="max-h-64 overflow-y-auto py-1">
            {shown.map((option, index) => (
              <li key={option.value || "none"}>
                <button
                  type="button"
                  role="option"
                  aria-selected={option.value === value}
                  disabled={option.disabled}
                  onMouseEnter={() => setActive(index)}
                  onClick={() => pick(option)}
                  className={`flex w-full items-baseline justify-between gap-3 px-3 py-1.5 text-left disabled:opacity-40 ${
                    index === active ? "bg-brand-soft" : ""
                  } ${option.value === value ? "font-medium" : ""}`}
                >
                  <span className="truncate">{option.label}</span>
                  {option.hint && <span className="shrink-0 text-xs text-muted">{option.hint}</span>}
                </button>
              </li>
            ))}
            {shown.length === 0 && (
              <li className="px-3 py-4 text-center text-muted">{loading ? "Loading…" : "Nothing matches."}</li>
            )}
          </ul>
          {footer && <div className="border-t border-line px-2 py-1.5">{footer(close)}</div>}
        </Card>,
        document.body,
      )}
    </div>
  );
}
