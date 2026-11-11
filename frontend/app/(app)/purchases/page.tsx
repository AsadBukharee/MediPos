"use client";

import { useState } from "react";
import { Button, DataTable, Field, Input, Modal, Notice, PageHeader, Select, Status, Tabs } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { date, dateTime, money, today } from "@/lib/format";
import { useAction, useDebounced, useList } from "@/lib/hooks";
import type { Grn, Product, PurchaseOrder, Supplier } from "@/lib/types";

export default function PurchasesPage() {
  const { can } = useAuth();
  const [tab, setTab] = useState<"grn" | "orders">("grn");
  const [receiving, setReceiving] = useState(false);
  const grns = useList<Grn>(tab === "grn" ? "/purchases/grns/" : null);
  const orders = useList<PurchaseOrder>(tab === "orders" ? "/purchases/orders/" : null);
  const { busy, error, run } = useAction();
  const post = async (path: string, reload: () => void) => {
    await run(() => api(path, { method: "POST" }));
    reload();
  };

  return (
    <>
      <PageHeader title="Purchases" subtitle="Stock increases only when a goods received note is confirmed.">
        <Tabs value={tab} onChange={setTab} options={[["grn", "Goods received"], ["orders", "Purchase orders"]]} />
        {can("purchases.receive") && <Button onClick={() => setReceiving(true)}>Receive goods</Button>}
      </PageHeader>
      <div className="mb-3"><Notice>{error}</Notice></div>

      {tab === "grn" ? (
        <DataTable
          rows={grns.rows}
          rowKey={(r) => r.id}
          loading={grns.loading}
          error={grns.error}
          empty="No goods received yet."
          columns={[
            { header: "GRN", cell: (r) => <span className="font-medium">{r.number}</span> },
            { header: "Supplier", cell: (r) => r.supplier_name },
            { header: "Supplier invoice", cell: (r) => r.supplier_invoice_number || "—" },
            { header: "Lines", cell: (r) => r.items.map((i) => `${i.product_name} ×${i.quantity} ${i.packaging_name?.toLowerCase()}`).join(", ") },
            { header: "Date", cell: (r) => dateTime(r.confirmed_at ?? r.created_at) },
            { header: "Status", cell: (r) => <Status value={r.status} /> },
            { header: "Total", align: "right", cell: (r) => money(r.total) },
            {
              header: "",
              align: "right",
              cell: (r) =>
                r.status === "draft" && can("purchases.receive") ? (
                  <span className="flex justify-end gap-1.5">
                    <Button size="sm" disabled={busy} onClick={() => post(`/purchases/grns/${r.id}/confirm/`, grns.reload)}>Confirm &amp; add stock</Button>
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => post(`/purchases/grns/${r.id}/cancel/`, grns.reload)}>Cancel</Button>
                  </span>
                ) : null,
            },
          ]}
        />
      ) : (
        <DataTable
          rows={orders.rows}
          rowKey={(r) => r.id}
          loading={orders.loading}
          error={orders.error}
          empty="No purchase orders yet. Approve an order list to create them."
          columns={[
            { header: "Order", cell: (r) => <span className="font-medium">{r.number}</span> },
            { header: "Supplier", cell: (r) => r.supplier_name },
            { header: "Lines", cell: (r) => r.items.map((i) => `${i.product_name} ×${i.quantity} ${i.packaging_name.toLowerCase()}`).join(", ") },
            { header: "Expected", cell: (r) => date(r.expected_date) },
            { header: "Status", cell: (r) => <Status value={r.status} /> },
            { header: "Total", align: "right", cell: (r) => money(r.total) },
            {
              header: "",
              align: "right",
              cell: (r) => (
                <span className="flex justify-end gap-1.5">
                  {r.status === "draft" && can("purchases.approve") && <Button size="sm" disabled={busy} onClick={() => post(`/purchases/orders/${r.id}/approve/`, orders.reload)}>Approve</Button>}
                  {r.status === "approved" && can("purchases.manage") && <Button size="sm" disabled={busy} onClick={() => post(`/purchases/orders/${r.id}/mark-ordered/`, orders.reload)}>Mark as sent</Button>}
                  {["draft", "approved", "ordered"].includes(r.status) && can("purchases.manage") && <Button size="sm" variant="ghost" disabled={busy} onClick={() => post(`/purchases/orders/${r.id}/cancel/`, orders.reload)}>Cancel</Button>}
                  <Button size="sm" variant="ghost" onClick={() => window.print()}>Print</Button>
                </span>
              ),
            },
          ]}
        />
      )}
      {receiving && <ReceiveModal onClose={() => (setReceiving(false), setTab("grn"), grns.reload())} />}
    </>
  );
}

interface Line {
  product: Product;
  packaging: string;
  quantity: string;
  unit_cost: string;
  batch_number: string;
  expiry_date: string;
}

function ReceiveModal({ onClose }: { onClose: () => void }) {
  const suppliers = useList<Supplier>("/suppliers/", { is_active: true, page_size: 200 });
  const [supplier, setSupplier] = useState("");
  const [invoice, setInvoice] = useState("");
  const [search, setSearch] = useState("");
  const [lines, setLines] = useState<Line[]>([]);
  const term = useDebounced(search);
  const results = useList<Product>(term.length >= 2 ? "/catalog/products/" : null, { search: term, is_active: true, page_size: 6 });
  const { busy, error, run } = useAction();

  const add = (product: Product) => {
    const pack = product.packagings.find((p) => p.is_default_purchase) ?? product.packagings[product.packagings.length - 1];
    setLines((rows) => [...rows, {
      product, packaging: String(pack.id), quantity: "1",
      unit_cost: (Number(product.purchase_price) * pack.factor).toFixed(2), batch_number: "", expiry_date: "",
    }]);
    setSearch("");
  };
  const update = (index: number, patch: Partial<Line>) => setLines((rows) => rows.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  const complete = lines.length > 0 && supplier && lines.every((l) => l.batch_number.trim() && l.expiry_date > today() && Number(l.quantity) > 0);

  const save = async (confirm: boolean) => {
    const done = await run(async () => {
      const grn = await api<Grn>("/purchases/grns/", {
        body: {
          supplier: Number(supplier),
          supplier_invoice_number: invoice,
          items: lines.map((l) => ({
            product: l.product.id, packaging: Number(l.packaging), quantity: Number(l.quantity),
            unit_cost: l.unit_cost || "0", batch_number: l.batch_number.trim(), expiry_date: l.expiry_date,
          })),
        },
      });
      if (confirm) await api(`/purchases/grns/${grn.id}/confirm/`, { method: "POST" });
      return grn;
    });
    if (done) onClose();
  };

  return (
    <Modal
      wide
      title="Receive goods"
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" disabled={!complete || busy} onClick={() => save(false)}>Save as draft</Button>
          <Button disabled={!complete || busy} onClick={() => save(true)}>Confirm &amp; add stock</Button>
        </>
      }
    >
      <div className="space-y-3">
        <Notice>{error}</Notice>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Supplier">
            <Select value={supplier} onChange={(e) => setSupplier(e.target.value)}>
              <option value="">Choose…</option>
              {suppliers.rows.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </Select>
          </Field>
          <Field label="Supplier invoice no."><Input value={invoice} onChange={(e) => setInvoice(e.target.value)} /></Field>
        </div>
        <Field label="Add medicine">
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search by name, SKU or barcode" />
        </Field>
        {results.rows.map((p) => (
          <button key={p.id} onClick={() => add(p)} className="block w-full rounded px-2.5 py-1.5 text-left hover:bg-canvas">
            {p.name} <span className="text-muted">{p.strength} · {p.sku}</span>
          </button>
        ))}
        {lines.length > 0 && (
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-line text-xs text-muted uppercase">
                {["Medicine", "Pack", "Qty", "Cost / pack", "Batch no.", "Expiry", ""].map((h) => <th key={h} className="py-2 pr-2 font-medium">{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {lines.map((line, index) => (
                <tr key={index} className="border-b border-line/70 last:border-0">
                  <td className="py-1.5 pr-2 font-medium">{line.product.name} <span className="font-normal text-muted">{line.product.strength}</span></td>
                  <td className="pr-2">
                    <Select value={line.packaging} onChange={(e) => update(index, { packaging: e.target.value })} className="h-8 w-28" aria-label="Pack">
                      {line.product.packagings.map((p) => <option key={p.id} value={p.id}>{p.unit_name}{p.factor > 1 ? ` ×${p.factor}` : ""}</option>)}
                    </Select>
                  </td>
                  <td className="pr-2"><Input type="number" min={1} step={1} value={line.quantity} onChange={(e) => update(index, { quantity: e.target.value })} className="num h-8 w-20" aria-label="Quantity" /></td>
                  <td className="pr-2"><Input inputMode="decimal" value={line.unit_cost} onChange={(e) => update(index, { unit_cost: e.target.value.replace(/[^\d.]/g, "") })} className="num h-8 w-24" aria-label="Cost per pack" /></td>
                  <td className="pr-2"><Input value={line.batch_number} onChange={(e) => update(index, { batch_number: e.target.value })} className="h-8 w-28 font-mono" aria-label="Batch number" /></td>
                  <td className="pr-2"><Input type="date" min={today()} value={line.expiry_date} onChange={(e) => update(index, { expiry_date: e.target.value })} className="h-8 w-36" aria-label="Expiry date" /></td>
                  <td><button aria-label="Remove line" className="px-1 text-muted hover:text-danger" onClick={() => setLines((rows) => rows.filter((_, i) => i !== index))}>✕</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="text-xs text-muted">Every line needs a batch number and a future expiry date. A draft does not change stock.</p>
      </div>
    </Modal>
  );
}
