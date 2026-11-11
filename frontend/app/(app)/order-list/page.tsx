"use client";

import { useState } from "react";
import { Button, Card, DataTable, Input, Notice, PageHeader, Select, Status } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateTime, qty } from "@/lib/format";
import { useAction, useApi, useList } from "@/lib/hooks";
import type { Requisition, StockAlert, Supplier } from "@/lib/types";

export default function OrderListPage() {
  const { can } = useAuth();
  const alerts = useList<StockAlert>("/notifications/alerts/", { status: "open" });
  const current = useApi<Requisition>("/purchases/requisitions/current/");
  const waiting = useList<Requisition>("/purchases/requisitions/", { status: "pending" });
  const approved = useList<Requisition>("/purchases/requisitions/", { status: "approved" });
  const suppliers = useList<Supplier>("/suppliers/", { is_active: true, page_size: 200 });
  const [quantities, setQuantities] = useState<Record<number, string>>({});
  const [done, setDone] = useState<string | null>(null);
  const { busy, error, run } = useAction();
  const reloadAll = () => (alerts.reload(), current.reload(), waiting.reload(), approved.reload());
  const act = async (action: () => Promise<unknown>, message?: string) => {
    const result = await run(action);
    if (result !== undefined || message) setDone(message ?? null);
    reloadAll();
  };
  const list = current.data;

  return (
    <>
      <PageHeader title="Alerts & order list" subtitle="Low-stock alerts become an order list, then purchase orders." />
      <div className="mb-3 space-y-2">
        <Notice>{error}</Notice>
        <Notice tone="ok">{done}</Notice>
      </div>

      <h2 className="mb-2 font-semibold">Stock alerts waiting for a decision</h2>
      <DataTable
        rows={alerts.rows}
        rowKey={(r) => r.id}
        loading={alerts.loading}
        error={alerts.error}
        empty="No open alerts. Stock is above every reorder level, or all alerts were handled."
        columns={[
          { header: "Medicine", cell: (r) => <span className="font-medium">{r.product_name}</span> },
          { header: "Alert", cell: (r) => <Status value={r.kind} /> },
          { header: "Left", align: "right", cell: (r) => `${qty(r.triggered_quantity)} ${r.base_unit_name.toLowerCase()}` },
          { header: "Reorder at", align: "right", cell: (r) => qty(r.reorder_level) },
          { header: "Raised", cell: (r) => dateTime(r.created_at) },
          {
            header: "Order quantity",
            cell: (r) => (
              <Input
                type="number" min={1} step={1} className="num h-8 w-28" aria-label={`Order quantity for ${r.product_name}`}
                value={quantities[r.id] ?? String(r.suggested_quantity)}
                onChange={(e) => setQuantities((q) => ({ ...q, [r.id]: e.target.value }))}
                disabled={!can("alerts.act")}
              />
            ),
          },
          {
            header: "",
            align: "right",
            cell: (r) =>
              can("alerts.act") && (
                <span className="flex justify-end gap-1.5">
                  <Button size="sm" disabled={busy} onClick={() => act(() => api(`/notifications/alerts/${r.id}/add-to-order/`, { body: { quantity: Number(quantities[r.id] ?? r.suggested_quantity) } }))}>
                    Add to order list
                  </Button>
                  <Button size="sm" variant="ghost" disabled={busy} onClick={() => act(() => api(`/notifications/alerts/${r.id}/skip/`, { method: "POST" }))}>
                    Skip
                  </Button>
                </span>
              ),
          },
        ]}
      />

      <div className="mt-6 mb-2 flex items-center justify-between">
        <h2 className="font-semibold">Order list {list?.number && <span className="font-normal text-muted">· {list.number}</span>}</h2>
        {list?.id && list.items.length > 0 && can("requisitions.manage") && (
          <Button disabled={busy} onClick={() => act(() => api(`/purchases/requisitions/${list.id}/submit/`, { method: "POST" }), "Sent for approval.")}>
            Send for approval
          </Button>
        )}
      </div>
      <DataTable
        rows={list?.items ?? []}
        rowKey={(r) => r.id}
        loading={current.loading}
        error={current.error}
        empty="The order list is empty. Add medicines from the alerts above."
        columns={[
          { header: "Medicine", cell: (r) => <span className="font-medium">{r.product_name}</span> },
          {
            header: "Quantity (base units)",
            cell: (r) => (
              <Input
                type="number" min={1} step={1} defaultValue={r.quantity} className="num h-8 w-28" aria-label={`Quantity of ${r.product_name}`}
                disabled={!can("requisitions.manage")}
                onBlur={(e) => Number(e.target.value) !== r.quantity && act(() => api(`/purchases/requisitions/items/${r.id}/`, { method: "PATCH", body: { quantity: Number(e.target.value) } }))}
              />
            ),
          },
          {
            header: "Supplier",
            cell: (r) => (
              <Select
                value={r.supplier ?? ""} className="h-8 w-52" aria-label={`Supplier for ${r.product_name}`} disabled={!can("requisitions.manage")}
                onChange={(e) => act(() => api(`/purchases/requisitions/items/${r.id}/`, { method: "PATCH", body: { supplier: e.target.value ? Number(e.target.value) : null } }))}
              >
                <option value="">Choose supplier…</option>
                {suppliers.rows.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </Select>
            ),
          },
          { header: "Requested by", cell: (r) => r.requested_by_name },
          {
            header: "",
            align: "right",
            cell: (r) => can("requisitions.manage") && (
              <Button size="sm" variant="ghost" onClick={() => act(() => api(`/purchases/requisitions/items/${r.id}/`, { method: "DELETE" }))}>Remove</Button>
            ),
          },
        ]}
      />

      {[...waiting.rows, ...approved.rows].length > 0 && (
        <>
          <h2 className="mt-6 mb-2 font-semibold">Requisitions in progress</h2>
          <div className="grid gap-3 lg:grid-cols-2">
            {[...waiting.rows, ...approved.rows].map((req) => (
              <Card key={req.id} className="p-4">
                <div className="flex items-center justify-between">
                  <p className="font-medium">{req.number} <Status value={req.status} /></p>
                  {can("purchases.approve") && req.status === "pending" && (
                    <span className="flex gap-1.5">
                      <Button size="sm" disabled={busy} onClick={() => act(() => api(`/purchases/requisitions/${req.id}/approve/`, { method: "POST" }))}>Approve</Button>
                      <Button size="sm" variant="ghost" disabled={busy} onClick={() => act(() => api(`/purchases/requisitions/${req.id}/reject/`, { method: "POST" }))}>Reject</Button>
                    </span>
                  )}
                  {can("purchases.approve") && req.status === "approved" && (
                    <Button size="sm" disabled={busy} onClick={() => act(() => api(`/purchases/requisitions/${req.id}/convert/`, { method: "POST" }), "Purchase orders created, one per supplier. Find them under Purchases.")}>
                      Create purchase orders
                    </Button>
                  )}
                </div>
                <ul className="mt-2 text-[13px] text-muted">
                  {req.items.map((item) => (
                    <li key={item.id} className="flex justify-between py-0.5">
                      <span>{item.product_name}</span>
                      <span className="num">{qty(item.quantity)} · {item.supplier_name || "no supplier"}</span>
                    </li>
                  ))}
                </ul>
              </Card>
            ))}
          </div>
        </>
      )}
    </>
  );
}
