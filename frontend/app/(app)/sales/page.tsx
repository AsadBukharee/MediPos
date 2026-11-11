"use client";

import { useState } from "react";
import { ReceiptModal } from "@/components/receipt";
import { Button, DataTable, Field, Input, Modal, Notice, PageHeader, Select, Status } from "@/components/ui";
import { api, newKey } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateTime, money } from "@/lib/format";
import { useAction, useApi, useDebounced, useList } from "@/lib/hooks";
import type { Sale, SaleSummary } from "@/lib/types";

export default function SalesPage() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("completed");
  const [openId, setOpenId] = useState<number | null>(null);
  const term = useDebounced(search);
  const sales = useList<SaleSummary>("/sales/", { search: term, status });

  return (
    <>
      <PageHeader title="Invoices" subtitle={`${sales.count} invoice(s)`}>
        <Input placeholder="Invoice no. or customer" value={search} onChange={(e) => setSearch(e.target.value)} className="w-56" />
        <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-36" aria-label="Status">
          <option value="completed">Completed</option>
          <option value="held">On hold</option>
          <option value="cancelled">Cancelled</option>
          <option value="">All</option>
        </Select>
      </PageHeader>
      <DataTable
        rows={sales.rows}
        rowKey={(row) => row.id}
        loading={sales.loading}
        error={sales.error}
        onRowClick={(row) => setOpenId(row.id)}
        empty="No invoices match."
        columns={[
          { header: "Invoice", cell: (r) => <span className="font-medium">{r.number ?? `Held #${r.id}`}</span> },
          { header: "Date", cell: (r) => dateTime(r.completed_at ?? r.created_at) },
          { header: "Customer", cell: (r) => r.customer_name || "Walk-in" },
          { header: "Cashier", cell: (r) => r.cashier_name },
          { header: "Status", cell: (r) => <Status value={r.status} /> },
          { header: "Total", align: "right", cell: (r) => money(r.total) },
        ]}
      />
      {openId && <SaleDetail id={openId} onClose={() => (setOpenId(null), sales.reload())} />}
    </>
  );
}

function SaleDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const { can } = useAuth();
  const sale = useApi<Sale>(`/sales/${id}/`);
  const [mode, setMode] = useState<"view" | "return" | "cancel" | "print">("view");
  const [quantities, setQuantities] = useState<Record<number, string>>({});
  const [damaged, setDamaged] = useState<Record<number, boolean>>({});
  const [reason, setReason] = useState("");
  const [refundMethod, setRefundMethod] = useState("cash");
  const [key] = useState(newKey);
  const { busy, error, run } = useAction();
  const data = sale.data;

  if (!data) return <Modal title="Invoice" onClose={onClose}>{sale.error ? <Notice>{sale.error}</Notice> : "Loading…"}</Modal>;
  if (mode === "print") return <ReceiptModal sale={data} onClose={() => setMode("view")} />;

  const submitReturn = async () => {
    const items = data.items
      .filter((item) => Number(quantities[item.id]) > 0)
      .map((item) => ({ sale_item: item.id, quantity_base: Number(quantities[item.id]), restock: !damaged[item.id] }));
    const done = await run(() =>
      api("/sales/returns/", { body: { sale: data.id, reason, refund_method: refundMethod, items }, idempotencyKey: key }),
    );
    if (done) onClose();
  };
  const submitCancel = async () => {
    const done = await run(() => api(`/sales/${data.id}/cancel/`, { body: { reason } }));
    if (done) onClose();
  };
  const returnable = data.status === "completed" && data.items.some((i) => i.returned_base < i.quantity_base);

  return (
    <Modal
      wide
      title={`${data.number ?? `Held #${data.id}`} · ${money(data.total)}`}
      onClose={onClose}
      footer={
        mode === "view" ? (
          <>
            {data.status === "completed" && can("sales.cancel") && <Button variant="ghost" onClick={() => setMode("cancel")}>Cancel invoice</Button>}
            {returnable && can("sales.return") && <Button variant="secondary" onClick={() => setMode("return")}>Return items</Button>}
            {data.status === "completed" && <Button onClick={() => setMode("print")}>Reprint</Button>}
          </>
        ) : (
          <>
            <Button variant="secondary" onClick={() => setMode("view")}>Back</Button>
            {mode === "return" ? (
              <Button disabled={busy || !reason.trim()} onClick={submitReturn}>Process return</Button>
            ) : (
              <Button variant="danger" disabled={busy || !reason.trim()} onClick={submitCancel}>Cancel invoice</Button>
            )}
          </>
        )
      }
    >
      <div className="space-y-3">
        <Notice>{error}</Notice>
        <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-muted">
          <Status value={data.status} />
          <span>{dateTime(data.completed_at ?? data.created_at)}</span>
          <span>{data.customer_name || "Walk-in"}</span>
          <span>Cashier {data.cashier_name}</span>
          <span>Paid by {data.payments.map((p) => `${p.method} ${money(p.amount)}`).join(", ") || "—"}</span>
        </p>
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-line text-xs text-muted uppercase">
              <th className="py-2 font-medium">Medicine</th>
              <th className="py-2 text-right font-medium">Sold</th>
              <th className="py-2 text-right font-medium">Returned</th>
              <th className="py-2 text-right font-medium">Total</th>
              {mode === "return" && <th className="py-2 pl-4 font-medium">Return now (base units)</th>}
            </tr>
          </thead>
          <tbody>
            {data.items.map((item) => {
              const left = item.quantity_base - item.returned_base;
              return (
                <tr key={item.id} className="border-b border-line/70 last:border-0">
                  <td className="py-2">{item.product_name}</td>
                  <td className="num py-2 text-right">{item.quantity} {item.packaging_name.toLowerCase()} ({item.quantity_base})</td>
                  <td className="num py-2 text-right">{item.returned_base}</td>
                  <td className="num py-2 text-right">{money(item.line_total)}</td>
                  {mode === "return" && (
                    <td className="py-1.5 pl-4">
                      <span className="flex items-center gap-2">
                        <Input
                          type="number" min={0} max={left} step={1} disabled={left === 0} placeholder={`max ${left}`}
                          value={quantities[item.id] ?? ""} aria-label={`Quantity of ${item.product_name} to return`}
                          onChange={(e) => setQuantities((q) => ({ ...q, [item.id]: e.target.value }))}
                          className="num h-8 w-24"
                        />
                        <label className="flex items-center gap-1 text-xs text-muted">
                          <input type="checkbox" checked={Boolean(damaged[item.id])} onChange={(e) => setDamaged((d) => ({ ...d, [item.id]: e.target.checked }))} />
                          Damaged (do not restock)
                        </label>
                      </span>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
        {mode !== "view" && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Reason">
              <Input value={reason} onChange={(e) => setReason(e.target.value)} autoFocus />
            </Field>
            {mode === "return" && (
              <Field label="Refund by">
                <Select value={refundMethod} onChange={(e) => setRefundMethod(e.target.value)}>
                  <option value="cash">Cash</option>
                  <option value="card">Card</option>
                  <option value="bank">Bank</option>
                  <option value="wallet">Wallet</option>
                  {data.customer && <option value="credit">Customer credit</option>}
                </Select>
              </Field>
            )}
          </div>
        )}
        {mode === "cancel" && <Notice tone="warn">Cancelling puts every item back into its batch and reverses the accounting entry. The invoice stays on record.</Notice>}
      </div>
    </Modal>
  );
}
