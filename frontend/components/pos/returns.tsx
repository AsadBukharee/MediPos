"use client";

import { useState } from "react";
import { Badge, Button, Card, Field, Input, Notice, Select } from "@/components/ui";
import { api, newKey } from "@/lib/api";
import { dateTime, money, qty } from "@/lib/format";
import { useAction, useApi, useDebounced, useList } from "@/lib/hooks";
import { PAYMENT_METHODS } from "@/lib/pos";
import type { Sale, SaleSummary } from "@/lib/types";

interface ReturnReceipt {
  id: number;
  number: string;
  total: string;
  refund_method: string;
  created_at: string;
  sale_number: string;
}

const BUSINESS = process.env.NEXT_PUBLIC_BUSINESS_NAME || "MediPos Pharmacy";

/** Take medicine back at the counter: find the invoice, choose the lines, refund. */
export function Returns({ onDone }: { onDone: () => void }) {
  const [search, setSearch] = useState("");
  const [openId, setOpenId] = useState<number | null>(null);
  const [done, setDone] = useState<ReturnReceipt | null>(null);
  const invoices = useList<SaleSummary>("/sales/", {
    search: useDebounced(search.trim()),
    status: "completed",
    page_size: 12,
  });

  if (done) return <Done receipt={done} onNext={() => (setDone(null), setOpenId(null), onDone())} />;
  if (openId) return <ReturnForm saleId={openId} onBack={() => setOpenId(null)} onDone={setDone} />;

  return (
    <Card className="p-4">
      <Field label="Find the invoice">
        <Input
          autoFocus
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Invoice number, customer name or phone"
          className="h-11 text-base"
        />
      </Field>
      <Notice>{invoices.error}</Notice>
      <ul className="mt-3 divide-y divide-line/70">
        {invoices.rows.map((sale) => (
          <li key={sale.id}>
            <button
              onClick={() => setOpenId(sale.id)}
              className="flex w-full items-center justify-between gap-3 px-1 py-2.5 text-left hover:bg-canvas"
            >
              <span>
                <span className="font-medium">{sale.number}</span>
                <span className="block text-[13px] text-muted">
                  {dateTime(sale.completed_at)} · {sale.customer_name || "Walk-in"} · {sale.cashier_name}
                </span>
              </span>
              <span className="num font-medium">{money(sale.total)}</span>
            </button>
          </li>
        ))}
      </ul>
      {!invoices.loading && invoices.rows.length === 0 && (
        <p className="py-10 text-center text-muted">
          {search ? "No invoice matches." : "No completed invoices in this branch yet."}
        </p>
      )}
    </Card>
  );
}

function ReturnForm({
  saleId,
  onBack,
  onDone,
}: {
  saleId: number;
  onBack: () => void;
  onDone: (receipt: ReturnReceipt) => void;
}) {
  const sale = useApi<Sale>(`/sales/${saleId}/`);
  const [quantities, setQuantities] = useState<Record<number, string>>({});
  const [damaged, setDamaged] = useState<Record<number, boolean>>({});
  const [reason, setReason] = useState("");
  const [method, setMethod] = useState("cash");
  const [key] = useState(newKey);
  const { busy, error, run } = useAction();
  const data = sale.data;

  if (!data) return <Card className="p-6">{sale.error ? <Notice>{sale.error}</Notice> : "Loading…"}</Card>;

  const chosen = data.items.filter((item) => Number(quantities[item.id]) > 0);
  const refund = chosen.reduce((sum, item) => {
    const left = item.quantity_base - item.returned_base;
    const taking = Math.min(Number(quantities[item.id]), left);
    const remaining = Number(item.line_total) - Number(item.refunded_amount);
    return sum + (taking === left ? remaining : (remaining * taking) / Math.max(left, 1));
  }, 0);

  const submit = async () => {
    const result = await run(() =>
      api<{ id: number; number: string; total: string }>("/sales/returns/", {
        body: {
          sale: data.id,
          reason,
          refund_method: method,
          items: chosen.map((item) => ({
            sale_item: item.id,
            quantity_base: Number(quantities[item.id]),
            restock: !damaged[item.id],
          })),
        },
        idempotencyKey: key,
      }),
    );
    if (result)
      onDone({ ...result, refund_method: method, created_at: new Date().toISOString(), sale_number: data.number ?? "" });
  };

  return (
    <Card className="p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="font-semibold">{data.number}</h2>
          <p className="text-[13px] text-muted">
            {dateTime(data.completed_at)} · {data.customer_name || "Walk-in"} · paid {money(data.total)}
          </p>
        </div>
        <Button variant="ghost" onClick={onBack}>
          ← Another invoice
        </Button>
      </div>
      <Notice>{error}</Notice>

      <table className="w-full text-left">
        <thead>
          <tr className="border-b border-line text-xs tracking-wide text-muted uppercase">
            <th className="py-2 font-medium">Medicine</th>
            <th className="py-2 text-right font-medium">Sold</th>
            <th className="py-2 text-right font-medium">Already back</th>
            <th className="py-2 pl-4 font-medium">Return now</th>
            <th className="py-2 pl-3 font-medium">Condition</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((item) => {
            const left = item.quantity_base - item.returned_base;
            return (
              <tr key={item.id} className="border-b border-line/70 last:border-0">
                <td className="py-2">
                  {item.product_name}
                  {left === 0 && (
                    <span className="ml-2">
                      <Badge>fully returned</Badge>
                    </span>
                  )}
                </td>
                <td className="num py-2 text-right">
                  {item.quantity} {item.packaging_name.toLowerCase()} ({qty(item.quantity_base)})
                </td>
                <td className="num py-2 text-right">{qty(item.returned_base)}</td>
                <td className="py-1.5 pl-4">
                  <span className="flex items-center gap-1.5">
                    <Input
                      type="number"
                      min={0}
                      max={left}
                      step={1}
                      disabled={left === 0}
                      placeholder="0"
                      aria-label={`Quantity of ${item.product_name} to return`}
                      value={quantities[item.id] ?? ""}
                      onChange={(event) => setQuantities({ ...quantities, [item.id]: event.target.value })}
                      className="num h-8 w-24"
                    />
                    {left > 0 && (
                      <button
                        className="text-xs font-medium text-brand hover:underline"
                        onClick={() => setQuantities({ ...quantities, [item.id]: String(left) })}
                      >
                        all {left}
                      </button>
                    )}
                  </span>
                </td>
                <td className="py-1.5 pl-3">
                  <label className="flex items-center gap-1.5 text-[13px] text-muted">
                    <input
                      type="checkbox"
                      checked={Boolean(damaged[item.id])}
                      onChange={(event) => setDamaged({ ...damaged, [item.id]: event.target.checked })}
                    />
                    Damaged — keep off the shelf
                  </label>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="mt-4 grid items-end gap-3 sm:grid-cols-[2fr_1fr_auto]">
        <Field label="Reason">
          <Input
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Why is it coming back?"
          />
        </Field>
        <Field label="Refund by">
          <Select value={method} onChange={(event) => setMethod(event.target.value)}>
            {PAYMENT_METHODS.filter(([value]) => value !== "credit" || data.customer).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </Field>
        <Button size="lg" disabled={busy || chosen.length === 0 || !reason.trim()} onClick={submit}>
          Refund {money(refund)}
        </Button>
      </div>
      <p className="mt-2 text-xs text-muted">
        Returned stock goes back into the batch it was sold from. Anything marked damaged is refunded but stays off the shelf.
      </p>
    </Card>
  );
}

function Done({ receipt, onNext }: { receipt: ReturnReceipt; onNext: () => void }) {
  return (
    <Card className="p-6">
      <div className="print-area mx-auto max-w-sm text-center">
        <p className="text-sm font-bold">{BUSINESS}</p>
        <p className="mb-3 text-[13px]">Credit note</p>
        <p className="num text-3xl font-semibold tracking-tight">{money(receipt.total)}</p>
        <p className="mt-1 text-muted">refunded by {receipt.refund_method}</p>
        <dl className="num mt-4 grid grid-cols-2 gap-y-1 border-t border-dashed border-current pt-3 text-left text-[13px]">
          <dt className="text-muted">Credit note</dt>
          <dd className="text-right">{receipt.number}</dd>
          <dt className="text-muted">Against invoice</dt>
          <dd className="text-right">{receipt.sale_number}</dd>
          <dt className="text-muted">Date</dt>
          <dd className="text-right">{dateTime(receipt.created_at)}</dd>
        </dl>
      </div>
      <div className="no-print mt-6 flex justify-center gap-2">
        <Button variant="secondary" onClick={() => window.print()}>
          Print credit note
        </Button>
        <Button onClick={onNext}>Another return</Button>
      </div>
    </Card>
  );
}
