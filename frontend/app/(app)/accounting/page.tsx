"use client";

import { useState } from "react";
import { Button, Card, DataTable, Field, Input, Modal, Notice, PageHeader, Select, Tabs } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { date, money, title, today } from "@/lib/format";
import { useAction, useApi, useList } from "@/lib/hooks";

type Tab = "trial_balance" | "profit_and_loss" | "balance_sheet" | "journal";

interface TrialBalance {
  rows: { code: string; name: string; type: string; debit: string; credit: string }[];
  total_debit: string;
  total_credit: string;
}

interface Entry {
  id: number;
  date: string;
  memo: string;
  source_number: string;
  lines: { id: number; account_code: string; account_name: string; debit: string; credit: string }[];
}

interface Account {
  id: number;
  code: string;
  name: string;
  type: string;
}

export default function AccountingPage() {
  const { can } = useAuth();
  const [tab, setTab] = useState<Tab>("trial_balance");
  const [from, setFrom] = useState(() => `${today().slice(0, 4)}-01-01`);
  const [to, setTo] = useState(today);
  const [expense, setExpense] = useState(false);
  const statement = useApi<TrialBalance & Record<string, string>>(
    tab === "journal" ? null : "/accounting/statements/",
    { statement: tab, date_from: tab === "balance_sheet" ? undefined : from, date_to: to },
  );
  const journal = useList<Entry>(tab === "journal" ? "/accounting/journal/" : null, { date__gte: from, date__lte: to, page_size: 50 });

  return (
    <>
      <PageHeader title="Accounting" subtitle="Double-entry ledger. Posted entries are reversed, never edited.">
        <Tabs value={tab} onChange={setTab} options={[["trial_balance", "Trial balance"], ["profit_and_loss", "Profit & loss"], ["balance_sheet", "Balance sheet"], ["journal", "General ledger"]]} />
        {tab !== "balance_sheet" && <Input type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} className="w-40" aria-label="From" />}
        <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="w-40" aria-label="To" />
        {can("accounting.manage") && <Button onClick={() => setExpense(true)}>Record expense</Button>}
      </PageHeader>
      <Notice>{statement.error ?? journal.error}</Notice>

      {tab === "trial_balance" && statement.data?.rows && (
        <DataTable
          rows={statement.data.rows}
          rowKey={(r) => r.code}
          empty="No postings in this period."
          columns={[
            { header: "Code", cell: (r) => <span className="font-mono text-[13px]">{r.code}</span> },
            { header: "Account", cell: (r) => <span className="font-medium">{r.name}</span> },
            { header: "Type", cell: (r) => title(r.type) },
            { header: "Debit", align: "right", cell: (r) => (Number(r.debit) ? money(r.debit) : "") },
            { header: "Credit", align: "right", cell: (r) => (Number(r.credit) ? money(r.credit) : "") },
          ]}
        />
      )}
      {tab === "trial_balance" && statement.data?.rows && (
        <p className="num mt-2 text-right font-semibold">
          Totals: {money(statement.data.total_debit)} debit · {money(statement.data.total_credit)} credit
        </p>
      )}

      {(tab === "profit_and_loss" || tab === "balance_sheet") && statement.data && !statement.data.rows && (
        <Card className="max-w-xl p-5">
          <dl className="num grid grid-cols-2 gap-y-2">
            {Object.entries(statement.data).map(([key, value]) => {
              const strong = ["gross_profit", "net_profit", "assets", "liabilities_and_equity"].includes(key);
              return (
                <span key={key} className={`contents ${strong ? "font-semibold" : ""}`}>
                  <dt className={strong ? "border-t border-line pt-2" : "text-muted"}>{title(key)}</dt>
                  <dd className={`text-right ${strong ? "border-t border-line pt-2" : ""}`}>{money(String(value))}</dd>
                </span>
              );
            })}
          </dl>
        </Card>
      )}

      {tab === "journal" && (
        <div className="space-y-2">
          {journal.rows.map((entry) => (
            <Card key={entry.id} className="p-3">
              <p className="flex justify-between">
                <span className="font-medium">{entry.memo}</span>
                <span className="text-muted">{date(entry.date)} · JE-{entry.id}</span>
              </p>
              <table className="num mt-1 w-full text-[13px]">
                <tbody>
                  {entry.lines.map((line) => (
                    <tr key={line.id}>
                      <td className={`py-0.5 ${Number(line.credit) ? "pl-8" : ""}`}>{line.account_code} {line.account_name}</td>
                      <td className="w-28 text-right">{Number(line.debit) ? money(line.debit) : ""}</td>
                      <td className="w-28 text-right">{Number(line.credit) ? money(line.credit) : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          ))}
          {!journal.loading && journal.rows.length === 0 && <p className="py-8 text-center text-muted">No entries in this period.</p>}
        </div>
      )}
      {expense && <ExpenseModal onClose={() => (setExpense(false), statement.reload(), journal.reload())} />}
    </>
  );
}

function ExpenseModal({ onClose }: { onClose: () => void }) {
  const accounts = useList<Account>("/accounting/accounts/");
  const [form, setForm] = useState({ account: "", amount: "", paid_from: "cash", description: "", date: today() });
  const { busy, error, run } = useAction();
  const save = async () => {
    const done = await run(() => api("/accounting/expenses/", { body: { ...form, account: Number(form.account) } }));
    if (done) onClose();
  };
  return (
    <Modal title="Record expense" onClose={onClose} footer={<Button disabled={busy || !form.account || !(Number(form.amount) > 0) || !form.description.trim()} onClick={save}>Save</Button>}>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2"><Notice>{error}</Notice></div>
        <Field label="Expense account">
          <Select value={form.account} onChange={(e) => setForm((f) => ({ ...f, account: e.target.value }))}>
            <option value="">Choose…</option>
            {accounts.rows.filter((a) => a.type === "expense").map((a) => <option key={a.id} value={a.id}>{a.code} {a.name}</option>)}
          </Select>
        </Field>
        <Field label="Amount"><Input inputMode="decimal" className="num" value={form.amount} onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value.replace(/[^\d.]/g, "") }))} /></Field>
        <Field label="Paid from">
          <Select value={form.paid_from} onChange={(e) => setForm((f) => ({ ...f, paid_from: e.target.value }))}>
            <option value="cash">Cash</option>
            <option value="bank">Bank</option>
          </Select>
        </Field>
        <Field label="Date"><Input type="date" value={form.date} max={today()} onChange={(e) => setForm((f) => ({ ...f, date: e.target.value }))} /></Field>
        <div className="sm:col-span-2"><Field label="Description"><Input value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} /></Field></div>
      </div>
    </Modal>
  );
}
