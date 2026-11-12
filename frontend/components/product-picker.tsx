"use client";

import { useEffect, useRef, useState } from "react";
import { Button, Card, Input } from "@/components/ui";
import { useDebounced, useList } from "@/lib/hooks";
import type { StockRow } from "@/lib/types";

export interface PickedProduct {
  id: number;
  label: string;
}

/** Searchable, checkable medicine list. Pick several; the caller keeps the order and colours. */
export function ProductPicker({
  selected,
  onChange,
  max = 8,
}: {
  selected: PickedProduct[];
  onChange: (next: PickedProduct[]) => void;
  max?: number;
}) {
  const [open, setOpen] = useState(false);
  const [term, setTerm] = useState("");
  const wrapper = useRef<HTMLDivElement>(null);
  const results = useList<StockRow>(open ? "/inventory/stock/" : null, {
    search: useDebounced(term.trim()),
    is_active: true,
    page_size: 25,
  });

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!wrapper.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const isSelected = (id: number) => selected.some((item) => item.id === id);
  const full = selected.length >= max;

  const toggle = (row: StockRow) => {
    if (isSelected(row.id)) onChange(selected.filter((item) => item.id !== row.id));
    else if (!full) onChange([...selected, { id: row.id, label: `${row.name} ${row.strength}`.trim() }]);
  };

  return (
    <div ref={wrapper} className="relative">
      <Button
        variant="secondary"
        aria-expanded={open}
        aria-haspopup="listbox"
        onClick={() => setOpen((value) => !value)}
      >
        {selected.length ? `${selected.length} medicine${selected.length > 1 ? "s" : ""} selected` : "Choose medicines"}
        <span aria-hidden className="text-muted">▾</span>
      </Button>

      {open && (
        <Card className="absolute z-20 mt-1 w-80 overflow-hidden p-0 shadow-lg">
          <div className="border-b border-line p-2">
            <Input
              autoFocus
              value={term}
              onChange={(event) => setTerm(event.target.value)}
              placeholder="Search by name, generic or SKU"
              aria-label="Search medicines"
            />
          </div>
          <ul role="listbox" aria-multiselectable className="max-h-72 overflow-y-auto py-1">
            {results.rows.map((row) => {
              const picked = isSelected(row.id);
              return (
                <li key={row.id}>
                  <label
                    className={`flex cursor-pointer items-center gap-2.5 px-3 py-2 hover:bg-canvas ${
                      !picked && full ? "cursor-not-allowed opacity-45" : ""
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={picked}
                      disabled={!picked && full}
                      onChange={() => toggle(row)}
                      className="size-4 shrink-0"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate">
                        {row.name} <span className="text-muted">{row.strength}</span>
                      </span>
                      <span className="block truncate text-xs text-muted">
                        {row.generic_name || row.sku}
                      </span>
                    </span>
                  </label>
                </li>
              );
            })}
            {!results.loading && results.rows.length === 0 && (
              <li className="px-3 py-6 text-center text-muted">No medicine matches.</li>
            )}
          </ul>
          <div className="flex items-center justify-between gap-2 border-t border-line px-3 py-2 text-[13px]">
            <span className="text-muted">
              {full ? `Limit of ${max} reached` : `${selected.length} of ${max} selected`}
            </span>
            <span className="flex gap-2">
              {selected.length > 0 && (
                <button className="font-medium text-brand hover:underline" onClick={() => onChange([])}>
                  Clear
                </button>
              )}
              <button className="font-medium text-brand hover:underline" onClick={() => setOpen(false)}>
                Done
              </button>
            </span>
          </div>
        </Card>
      )}
    </div>
  );
}
