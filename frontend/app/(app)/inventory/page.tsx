"use client";

import { useState } from "react";
import { Badge, Button, DataTable, Field, Input, Modal, Notice, PageHeader, Select, Status, Tabs } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { date, dateTime, daysUntil, money, qty, title } from "@/lib/format";
import { useAction, useApi, useDebounced, useList } from "@/lib/hooks";
import type { Batch, Row, StockRow } from "@/lib/types";

type Tab = "stock" | "expiry" | "ledger" | "adjustments";

export default function InventoryPage() {
  // Deep links from the dashboard: /inventory?state=low, /inventory?tab=expiry.
  // This page only ever renders in the browser (the app shell waits for the session first).
  const query = () => new URLSearchParams(typeof window === "undefined" ? "" : window.location.search);
  const [tab, setTab] = useState<Tab>(() => (query().get("tab") as Tab) || "stock");
  const [state, setState] = useState(() => query().get("state") ?? "");

  return (
    <>
      <PageHeader title="Inventory" subtitle="Batch-wise stock for this branch">
        <Tabs value={tab} onChange={setTab} options={[["stock", "Current stock"], ["expiry", "Expiry"], ["ledger", "Stock ledger"], ["adjustments", "Adjustments"]]} />
      </PageHeader>
      {tab === "stock" && <StockTab state={state} setState={setState} />}
      {tab === "expiry" && <ExpiryTab />}
      {tab === "ledger" && <LedgerTab />}
      {tab === "adjustments" && <AdjustmentsTab />}
    </>
  );
}

function StockTab({ state, setState }: { state: string; setState: (s: string) => void }) {
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState<StockRow | null>(null);
  const stock = useList<StockRow>("/inventory/stock/", { search: useDebounced(search), state, is_active: true });
  return (
    <>
      <div className="mb-3 flex flex-wrap gap-2">
        <Input placeholder="Search medicine, SKU or barcode" value={search} onChange={(e) => setSearch(e.target.value)} className="w-72" />
        <Select value={state} onChange={(e) => setState(e.target.value)} className="w-40" aria-label="Stock state">
          <option value="">All medicines</option>
          <option value="in">In stock</option>
          <option value="low">Low stock</option>
          <option value="out">Out of stock</option>
        </Select>
      </div>
      <DataTable
        rows={stock.rows}
        rowKey={(r) => r.id}
        loading={stock.loading}
        error={stock.error}
        onRowClick={setOpen}
        columns={[
          { header: "Medicine", cell: (r) => (<><span className="font-medium">{r.name}</span> <span className="text-muted">{r.strength}</span></>) },
          { header: "SKU", cell: (r) => <span className="font-mono text-[13px]">{r.sku}</span> },
          { header: "Sellable", align: "right", cell: (r) => `${qty(r.sellable)} ${r.base_unit_name.toLowerCase()}` },
          { header: "On hand", align: "right", cell: (r) => (r.on_hand !== r.sellable ? <span className="text-warn">{qty(r.on_hand)}</span> : qty(r.on_hand)) },
          { header: "Reorder at", align: "right", cell: (r) => r.reorder_level || "—" },
          { header: "Next expiry", cell: (r) => date(r.nearest_expiry) },
          { header: "State", cell: (r) => <Status value={r.state} /> },
        ]}
      />
      {open && <BatchesModal row={open} onClose={() => (setOpen(null), stock.reload())} />}
    </>
  );
}

function BatchesModal({ row, onClose }: { row: StockRow; onClose: () => void }) {
  const { can } = useAuth();
  const batches = useList<Batch>(`/inventory/stock/${row.id}/batches/`);
  const { error, run } = useAction();
  const toggle = async (batch: Batch) => {
    const blocking = batch.status === "active";
    const reason = blocking ? window.prompt("Why is this batch being blocked?") : "Released";
    if (!reason) return;
    await run(() => api(`/inventory/batches/${batch.id}/status/`, { body: { status: blocking ? "blocked" : "active", reason } }));
    batches.reload();
  };
  return (
    <Modal wide title={`${row.name} ${row.strength} — batches`} onClose={onClose}>
      <Notice>{error ?? batches.error}</Notice>
      <table className="w-full text-left">
        <thead>
          <tr className="border-b border-line text-xs text-muted uppercase">
            <th className="py-2 font-medium">Batch</th>
            <th className="py-2 font-medium">Expiry</th>
            <th className="py-2 text-right font-medium">Quantity</th>
            <th className="py-2 text-right font-medium">Cost</th>
            <th className="py-2 pl-4 font-medium">Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {batches.rows.map((batch) => (
            <tr key={batch.id} className="border-b border-line/70 last:border-0">
              <td className="py-2 font-mono text-[13px]">{batch.batch_number}</td>
              <td className="py-2">{date(batch.expiry_date)} {batch.is_expired && <Badge tone="danger">expired</Badge>}</td>
              <td className="num py-2 text-right">{qty(batch.quantity_on_hand)}</td>
              <td className="num py-2 text-right">{money(batch.purchase_cost)}</td>
              <td className="py-2 pl-4"><Status value={batch.status} /></td>
              <td className="py-1.5 text-right">
                {can("inventory.adjust") && (
                  <Button size="sm" variant="ghost" onClick={() => toggle(batch)}>{batch.status === "active" ? "Block" : "Release"}</Button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!batches.loading && batches.rows.length === 0 && <p className="py-6 text-center text-muted">No stock in this branch.</p>}
      <p className="mt-3 text-xs text-muted">Sales take the earliest-expiring active batch first. Expired and blocked batches are never sold.</p>
    </Modal>
  );
}

function ExpiryTab() {
  const [report, setReport] = useState("near_expiry");
  const [days, setDays] = useState("90");
  const data = useApi<{ rows: Row[] }>("/reports/inventory/", { report, days });
  const rows = data.data?.rows ?? [];
  return (
    <>
      <div className="mb-3 flex gap-2">
        <Select value={report} onChange={(e) => setReport(e.target.value)} className="w-44" aria-label="Report">
          <option value="near_expiry">Expiring soon</option>
          <option value="expired">Already expired</option>
        </Select>
        {report === "near_expiry" && (
          <Select value={days} onChange={(e) => setDays(e.target.value)} className="w-36" aria-label="Window">
            <option value="30">Within 30 days</option>
            <option value="60">Within 60 days</option>
            <option value="90">Within 90 days</option>
          </Select>
        )}
      </div>
      <DataTable
        rows={rows}
        rowKey={(r) => String(r.batch)}
        loading={data.loading}
        error={data.error}
        empty={report === "expired" ? "No expired stock on the shelf." : "Nothing expiring in this window."}
        columns={[
          { header: "Medicine", cell: (r) => <span className="font-medium">{r.name}</span> },
          { header: "Batch", cell: (r) => <span className="font-mono text-[13px]">{r.batch_number}</span> },
          { header: "Expiry", cell: (r) => date(String(r.expiry_date)) },
          {
            header: "Days left",
            align: "right",
            cell: (r) => {
              const left = daysUntil(String(r.expiry_date)) ?? 0;
              return <span className={left <= 0 ? "text-danger" : left <= 30 ? "text-warn" : ""}>{left <= 0 ? "expired" : left}</span>;
            },
          },
          { header: "Quantity", align: "right", cell: (r) => qty(Number(r.quantity)) },
          { header: "Value at cost", align: "right", cell: (r) => money(r.value) },
        ]}
      />
    </>
  );
}

interface Movement {
  id: number;
  product_name: string;
  batch_number: string;
  movement_type: string;
  quantity: number;
  balance_after: number;
  source_number: string;
  source_type: string;
  user_name: string;
  created_at: string;
}

function LedgerTab() {
  const [type, setType] = useState("");
  const ledger = useList<Movement>("/inventory/movements/", { movement_type: type, page_size: 50 });
  return (
    <>
      <div className="mb-3">
        <Select value={type} onChange={(e) => setType(e.target.value)} className="w-52" aria-label="Movement type">
          <option value="">All movements</option>
          {["opening", "purchase_receipt", "purchase_return", "sale", "sale_return", "sale_cancel", "adjustment"].map((t) => (
            <option key={t} value={t}>{title(t)}</option>
          ))}
        </Select>
      </div>
      <DataTable
        rows={ledger.rows}
        rowKey={(r) => r.id}
        loading={ledger.loading}
        error={ledger.error}
        columns={[
          { header: "When", cell: (r) => dateTime(r.created_at) },
          { header: "Medicine", cell: (r) => <span className="font-medium">{r.product_name}</span> },
          { header: "Batch", cell: (r) => <span className="font-mono text-[13px]">{r.batch_number}</span> },
          { header: "Movement", cell: (r) => title(r.movement_type) },
          { header: "Document", cell: (r) => r.source_number || r.source_type },
          { header: "Change", align: "right", cell: (r) => <span className={r.quantity < 0 ? "text-danger" : "text-ok"}>{r.quantity > 0 ? "+" : ""}{qty(r.quantity)}</span> },
          { header: "Batch balance", align: "right", cell: (r) => qty(r.balance_after) },
          { header: "By", cell: (r) => r.user_name },
        ]}
      />
    </>
  );
}

interface Adjustment {
  id: number;
  number: string;
  reason: string;
  note: string;
  status: string;
  requested_by_name: string;
  created_at: string;
  items: { id: number; product_name: string; batch_number: string; quantity_delta: number }[];
}

function AdjustmentsTab() {
  const { can } = useAuth();
  const adjustments = useList<Adjustment>("/inventory/adjustments/");
  const [creating, setCreating] = useState(false);
  const { error, run } = useAction();
  const decide = async (id: number, action: "approve" | "reject") => {
    await run(() => api(`/inventory/adjustments/${id}/${action}/`, { method: "POST" }));
    adjustments.reload();
  };
  return (
    <>
      <div className="mb-3 flex items-center justify-between gap-3">
        <Notice>{error}</Notice>
        <span />
        {can("inventory.adjust") && <Button onClick={() => setCreating(true)}>New adjustment</Button>}
      </div>
      <DataTable
        rows={adjustments.rows}
        rowKey={(r) => r.id}
        loading={adjustments.loading}
        error={adjustments.error}
        empty="No stock adjustments yet."
        columns={[
          { header: "Number", cell: (r) => <span className="font-medium">{r.number}</span> },
          { header: "Date", cell: (r) => dateTime(r.created_at) },
          { header: "Reason", cell: (r) => (<>{title(r.reason)} <span className="text-muted">{r.note}</span></>) },
          { header: "Lines", cell: (r) => r.items.map((i) => `${i.product_name} ${i.quantity_delta > 0 ? "+" : ""}${i.quantity_delta}`).join(", ") },
          { header: "By", cell: (r) => r.requested_by_name },
          { header: "Status", cell: (r) => <Status value={r.status} /> },
          {
            header: "",
            align: "right",
            cell: (r) =>
              r.status === "pending" && can("inventory.adjust.approve") ? (
                <span className="flex justify-end gap-1.5">
                  <Button size="sm" onClick={() => decide(r.id, "approve")}>Approve</Button>
                  <Button size="sm" variant="ghost" onClick={() => decide(r.id, "reject")}>Reject</Button>
                </span>
              ) : null,
          },
        ]}
      />
      {creating && <AdjustmentForm onClose={() => (setCreating(false), adjustments.reload())} />}
    </>
  );
}

function AdjustmentForm({ onClose }: { onClose: () => void }) {
  const [search, setSearch] = useState("");
  const [product, setProduct] = useState<StockRow | null>(null);
  const [batch, setBatch] = useState("");
  const [delta, setDelta] = useState("");
  const [reason, setReason] = useState("damaged");
  const [note, setNote] = useState("");
  const term = useDebounced(search);
  const results = useList<StockRow>(term.length >= 2 && !product ? "/inventory/stock/" : null, { search: term, page_size: 6 });
  const batches = useList<Batch>(product ? `/inventory/stock/${product.id}/batches/` : null);
  const { busy, error, run } = useAction();
  const save = async () => {
    const done = await run(() =>
      api("/inventory/adjustments/", { body: { reason, note, items: [{ batch: Number(batch), quantity_delta: Number(delta) }] } }),
    );
    if (done) onClose();
  };
  return (
    <Modal
      title="New stock adjustment"
      onClose={onClose}
      footer={<Button disabled={busy || !batch || !Number(delta)} onClick={save}>Send for approval</Button>}
    >
      <div className="space-y-3">
        <Notice>{error}</Notice>
        <Field label="Medicine">
          {product ? (
            <p className="flex items-center justify-between rounded-md border border-line px-2.5 py-2">
              <span className="font-medium">{product.name} {product.strength}</span>
              <button className="text-[13px] text-brand" onClick={() => (setProduct(null), setBatch(""))}>Change</button>
            </p>
          ) : (
            <>
              <Input autoFocus value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search…" />
              {results.rows.map((row) => (
                <button key={row.id} onClick={() => setProduct(row)} className="block w-full rounded px-2.5 py-1.5 text-left hover:bg-canvas">
                  {row.name} <span className="text-muted">{row.strength} · {qty(row.on_hand)} on hand</span>
                </button>
              ))}
            </>
          )}
        </Field>
        <Field label="Batch">
          <Select value={batch} onChange={(e) => setBatch(e.target.value)} disabled={!product}>
            <option value="">Choose…</option>
            {batches.rows.map((b) => (
              <option key={b.id} value={b.id}>{b.batch_number} · exp {date(b.expiry_date)} · {qty(b.quantity_on_hand)} on hand</option>
            ))}
          </Select>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Change in base units" hint="Negative removes stock, e.g. -5">
            <Input type="number" step={1} value={delta} onChange={(e) => setDelta(e.target.value)} className="num" />
          </Field>
          <Field label="Reason">
            <Select value={reason} onChange={(e) => setReason(e.target.value)}>
              {["damaged", "lost", "expired", "count", "other"].map((r) => <option key={r} value={r}>{title(r)}</option>)}
            </Select>
          </Field>
        </div>
        <Field label="Note"><Input value={note} onChange={(e) => setNote(e.target.value)} /></Field>
        <p className="text-xs text-muted">Stock changes only after a manager approves the adjustment.</p>
      </div>
    </Modal>
  );
}
