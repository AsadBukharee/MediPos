"use client";

import { useState } from "react";
import { PaymentModal } from "@/components/party";
import { Button, DataTable, Field, Input, Modal, Notice, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateTime, money, title } from "@/lib/format";
import { useAction, useApi, useDebounced, useList } from "@/lib/hooks";
import type { Supplier } from "@/lib/types";

export default function SuppliersPage() {
  const { can } = useAuth();
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<Supplier | "new" | null>(null);
  const [paying, setPaying] = useState<Supplier | null>(null);
  const [ledger, setLedger] = useState<Supplier | null>(null);
  const suppliers = useList<Supplier>("/suppliers/", { search: useDebounced(search) });
  return (
    <>
      <PageHeader title="Suppliers" subtitle={`${suppliers.count} supplier(s)`}>
        <Input placeholder="Search suppliers" value={search} onChange={(e) => setSearch(e.target.value)} className="w-56" />
        {can("suppliers.manage") && <Button onClick={() => setEditing("new")}>New supplier</Button>}
      </PageHeader>
      <DataTable
        rows={suppliers.rows}
        rowKey={(r) => r.id}
        loading={suppliers.loading}
        error={suppliers.error}
        columns={[
          { header: "Supplier", cell: (r) => <span className="font-medium">{r.name}</span> },
          { header: "Contact", cell: (r) => [r.contact_person, r.phone].filter(Boolean).join(" · ") || "—" },
          { header: "We owe", align: "right", cell: (r) => <span className={Number(r.balance) > 0 ? "font-medium text-warn" : ""}>{money(r.balance)}</span> },
          {
            header: "",
            align: "right",
            cell: (r) => (
              <span className="flex justify-end gap-1.5">
                <Button size="sm" variant="ghost" onClick={() => setLedger(r)}>Ledger</Button>
                {can("suppliers.pay") && <Button size="sm" variant="secondary" onClick={() => setPaying(r)}>Pay</Button>}
                {can("suppliers.manage") && <Button size="sm" variant="ghost" onClick={() => setEditing(r)}>Edit</Button>}
              </span>
            ),
          },
        ]}
      />
      {editing && <SupplierForm supplier={editing === "new" ? null : editing} onClose={() => (setEditing(null), suppliers.reload())} />}
      {paying && <PaymentModal kind="supplier" party={paying} onClose={() => (setPaying(null), suppliers.reload())} />}
      {ledger && <LedgerModal supplier={ledger} onClose={() => setLedger(null)} />}
    </>
  );
}

function SupplierForm({ supplier, onClose }: { supplier: Supplier | null; onClose: () => void }) {
  const [form, setForm] = useState({
    name: supplier?.name ?? "", contact_person: supplier?.contact_person ?? "", phone: supplier?.phone ?? "",
    email: supplier?.email ?? "", address: supplier?.address ?? "", opening_balance: supplier?.opening_balance ?? "0",
  });
  const { busy, error, run } = useAction();
  const bind = (name: keyof typeof form) => ({ value: form[name], onChange: (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [name]: e.target.value })) });
  const save = async () => {
    const done = await run(() => (supplier ? api(`/suppliers/${supplier.id}/`, { method: "PATCH", body: form }) : api("/suppliers/", { body: form })));
    if (done) onClose();
  };
  return (
    <Modal title={supplier ? `Edit ${supplier.name}` : "New supplier"} onClose={onClose} footer={<Button disabled={busy || !form.name.trim()} onClick={save}>Save</Button>}>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2"><Notice>{error}</Notice></div>
        <Field label="Name"><Input {...bind("name")} autoFocus /></Field>
        <Field label="Contact person"><Input {...bind("contact_person")} /></Field>
        <Field label="Phone"><Input {...bind("phone")} /></Field>
        <Field label="Email"><Input type="email" {...bind("email")} /></Field>
        <Field label="Address"><Input {...bind("address")} /></Field>
        <Field label="Opening balance (we owe)"><Input {...bind("opening_balance")} inputMode="decimal" className="num" /></Field>
      </div>
    </Modal>
  );
}

interface LedgerRow {
  date: string;
  type: string;
  reference: string;
  debit: string;
  credit: string;
  balance: string;
}

function LedgerModal({ supplier, onClose }: { supplier: Supplier; onClose: () => void }) {
  const ledger = useApi<LedgerRow[]>(`/suppliers/${supplier.id}/ledger/`);
  return (
    <Modal wide title={`${supplier.name} — ledger`} onClose={onClose} footer={<Button variant="secondary" onClick={() => window.print()}>Print</Button>}>
      <Notice>{ledger.error}</Notice>
      <table className="print-area w-full text-left">
        <thead>
          <tr className="border-b border-line text-xs text-muted uppercase">
            <th className="py-2 font-medium">Date</th>
            <th className="py-2 font-medium">Entry</th>
            <th className="py-2 text-right font-medium">Paid / returned</th>
            <th className="py-2 text-right font-medium">Purchased</th>
            <th className="py-2 text-right font-medium">Balance</th>
          </tr>
        </thead>
        <tbody>
          {(ledger.data ?? []).map((row, index) => (
            <tr key={index} className="border-b border-line/70 last:border-0">
              <td className="py-2">{dateTime(row.date)}</td>
              <td className="py-2">{title(row.type)} {row.reference}</td>
              <td className="num py-2 text-right">{Number(row.debit) ? money(row.debit) : ""}</td>
              <td className="num py-2 text-right">{Number(row.credit) ? money(row.credit) : ""}</td>
              <td className="num py-2 text-right font-medium">{money(row.balance)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Modal>
  );
}
