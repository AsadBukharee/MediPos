"use client";

import { useState } from "react";
import { PaymentModal } from "@/components/party";
import { Badge, Button, DataTable, Field, Input, Modal, Notice, PageHeader, Select } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { money } from "@/lib/format";
import { useAction, useDebounced, useList } from "@/lib/hooks";
import type { Customer } from "@/lib/types";

export default function CustomersPage() {
  const { can } = useAuth();
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<Customer | "new" | null>(null);
  const [paying, setPaying] = useState<Customer | null>(null);
  const customers = useList<Customer>("/customers/", { search: useDebounced(search) });
  return (
    <>
      <PageHeader title="Customers" subtitle={`${customers.count} customer(s)`}>
        <Input placeholder="Name or phone" value={search} onChange={(e) => setSearch(e.target.value)} className="w-56" />
        {can("customers.manage") && <Button onClick={() => setEditing("new")}>New customer</Button>}
      </PageHeader>
      <DataTable
        rows={customers.rows}
        rowKey={(r) => r.id}
        loading={customers.loading}
        error={customers.error}
        empty="No customers yet. Walk-in sales do not need one."
        columns={[
          { header: "Customer", cell: (r) => <span className="font-medium">{r.name}</span> },
          { header: "Phone", cell: (r) => r.phone || "—" },
          { header: "Price tier", cell: (r) => <Badge tone={r.price_tier === "wholesale" ? "brand" : "neutral"}>{r.price_tier}</Badge> },
          { header: "Credit limit", align: "right", cell: (r) => money(r.credit_limit) },
          { header: "Owes us", align: "right", cell: (r) => <span className={Number(r.balance) > 0 ? "font-medium text-warn" : ""}>{money(r.balance)}</span> },
          {
            header: "",
            align: "right",
            cell: (r) => can("customers.manage") && (
              <span className="flex justify-end gap-1.5">
                {Number(r.balance) > 0 && <Button size="sm" variant="secondary" onClick={() => setPaying(r)}>Receive payment</Button>}
                <Button size="sm" variant="ghost" onClick={() => setEditing(r)}>Edit</Button>
              </span>
            ),
          },
        ]}
      />
      {editing && <CustomerForm customer={editing === "new" ? null : editing} onClose={() => (setEditing(null), customers.reload())} />}
      {paying && <PaymentModal kind="customer" party={paying} onClose={() => (setPaying(null), customers.reload())} />}
    </>
  );
}

function CustomerForm({ customer, onClose }: { customer: Customer | null; onClose: () => void }) {
  const [form, setForm] = useState({
    name: customer?.name ?? "", phone: customer?.phone ?? "", price_tier: customer?.price_tier ?? "retail",
    credit_limit: customer?.credit_limit ?? "0",
  });
  const { busy, error, run } = useAction();
  const save = async () => {
    const done = await run(() => (customer ? api(`/customers/${customer.id}/`, { method: "PATCH", body: form }) : api("/customers/", { body: form })));
    if (done) onClose();
  };
  return (
    <Modal title={customer ? `Edit ${customer.name}` : "New customer"} onClose={onClose} footer={<Button disabled={busy || !form.name.trim()} onClick={save}>Save</Button>}>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2"><Notice>{error}</Notice></div>
        <Field label="Name"><Input autoFocus value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} /></Field>
        <Field label="Phone"><Input value={form.phone} onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))} /></Field>
        <Field label="Price tier">
          <Select value={form.price_tier} onChange={(e) => setForm((f) => ({ ...f, price_tier: e.target.value as Customer["price_tier"] }))}>
            <option value="retail">Retail</option>
            <option value="wholesale">Wholesale</option>
          </Select>
        </Field>
        <Field label="Credit limit" hint="0 means no credit sales."><Input inputMode="decimal" className="num" value={form.credit_limit} onChange={(e) => setForm((f) => ({ ...f, credit_limit: e.target.value }))} /></Field>
      </div>
    </Modal>
  );
}
