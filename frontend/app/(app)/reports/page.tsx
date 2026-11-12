"use client";

import Link from "next/link";
import { useState } from "react";
import { Button, Card, Input, Notice, PageHeader, Select, Stat } from "@/components/ui";
import { download } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { money, title, today } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Row } from "@/lib/types";

const REPORTS: { id: string; label: string; path: string; params: Record<string, string>; dated: boolean; group: string }[] = [
  { id: "sales-day", label: "Sales by day", path: "/reports/sales/", params: { group: "day" }, dated: true, group: "Sales" },
  { id: "sales-product", label: "Sales and profit by medicine", path: "/reports/sales/", params: { group: "product" }, dated: true, group: "Sales" },
  { id: "sales-category", label: "Sales and profit by category", path: "/reports/sales/", params: { group: "category" }, dated: true, group: "Sales" },
  { id: "sales-cashier", label: "Sales by cashier", path: "/reports/sales/", params: { group: "cashier" }, dated: true, group: "Sales" },
  { id: "sales-customer", label: "Sales by customer", path: "/reports/sales/", params: { group: "customer" }, dated: true, group: "Sales" },
  { id: "sales-payment", label: "Payments by method", path: "/reports/sales/", params: { group: "payment_method" }, dated: true, group: "Sales" },
  { id: "purchases-supplier", label: "Purchases by supplier", path: "/reports/purchases/", params: { group: "supplier" }, dated: true, group: "Purchases" },
  { id: "purchases-product", label: "Purchases by medicine", path: "/reports/purchases/", params: { group: "product" }, dated: true, group: "Purchases" },
  { id: "valuation", label: "Stock valuation", path: "/reports/inventory/", params: { report: "valuation" }, dated: false, group: "Inventory" },
  { id: "low", label: "Low stock", path: "/reports/inventory/", params: { report: "low_stock" }, dated: false, group: "Inventory" },
  { id: "out", label: "Out of stock", path: "/reports/inventory/", params: { report: "out_of_stock" }, dated: false, group: "Inventory" },
  { id: "fast", label: "Fast-moving (30 days)", path: "/reports/inventory/", params: { report: "fast_moving" }, dated: false, group: "Inventory" },
  { id: "slow", label: "Slow-moving (30 days)", path: "/reports/inventory/", params: { report: "slow_moving" }, dated: false, group: "Inventory" },
  { id: "dead", label: "Dead stock (no sales in 90 days)", path: "/reports/inventory/", params: { report: "dead_stock", days: "90" }, dated: false, group: "Inventory" },
];
const MONEY_COLUMNS = new Set(["total", "revenue", "cost", "profit", "discount", "value"]);
const HIDDEN = new Set(["key", "product", "batch"]);

interface Totals {
  invoices: number;
  net_sales: string;
  returns_total: string;
  discounts: string;
  tax: string;
  gross_profit: string;
}

export default function ReportsPage() {
  const { user } = useAuth();
  const [reportId, setReportId] = useState("sales-day");
  const [from, setFrom] = useState(() => `${today().slice(0, 8)}01`);
  const [to, setTo] = useState(today);
  const [consolidated, setConsolidated] = useState(false);
  const report = REPORTS.find((r) => r.id === reportId)!;
  const params = {
    ...report.params,
    ...(report.dated ? { date_from: from, date_to: to, consolidated: consolidated ? 1 : undefined } : {}),
  };
  const table = useApi<{ rows: Row[] }>(report.path, params);
  const totals = useApi<Totals>("/reports/sales/", { date_from: from, date_to: to, consolidated: consolidated ? 1 : undefined });
  const rows = table.data?.rows ?? [];
  const columns = rows.length ? Object.keys(rows[0]).filter((c) => !HIDDEN.has(c)) : [];

  return (
    <>
      <PageHeader title="Reports">
        <Select value={reportId} onChange={(e) => setReportId(e.target.value)} className="w-72" aria-label="Report">
          {[...new Set(REPORTS.map((r) => r.group))].map((group) => (
            <optgroup key={group} label={group}>
              {REPORTS.filter((r) => r.group === group).map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
            </optgroup>
          ))}
        </Select>
        <Input type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} className="w-40" aria-label="From" />
        <Input type="date" value={to} min={from} onChange={(e) => setTo(e.target.value)} className="w-40" aria-label="To" />
        {(user?.branches.length ?? 0) > 1 && (
          <label className="flex items-center gap-1.5 text-[13px]">
            <input type="checkbox" checked={consolidated} onChange={(e) => setConsolidated(e.target.checked)} /> All my branches
          </label>
        )}
        <Button variant="secondary" onClick={() => download(report.path, params, `${report.id}.csv`)}>Export CSV</Button>
        <Button variant="secondary" onClick={() => window.print()}>Print</Button>
        <Link href="/reports/trends" className="text-[13px] font-medium text-brand hover:underline">
          Sales trends chart
        </Link>
      </PageHeader>

      {totals.data && (
        <div className="mb-4 grid gap-3 sm:grid-cols-3 xl:grid-cols-6">
          <Stat label="Invoices" value={totals.data.invoices} />
          <Stat label="Net sales" value={money(totals.data.net_sales)} />
          <Stat label="Returns" value={money(totals.data.returns_total)} />
          <Stat label="Discounts given" value={money(totals.data.discounts)} />
          <Stat label="Tax collected" value={money(totals.data.tax)} />
          <Stat label="Gross profit" value={money(totals.data.gross_profit)} tone="ok" />
        </div>
      )}

      <Notice>{table.error}</Notice>
      <Card className="print-area overflow-x-auto">
        <p className="border-b border-line px-3 py-2.5 font-semibold">
          {report.label} {report.dated && <span className="font-normal text-muted">· {from} to {to}</span>}
        </p>
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-line text-xs text-muted uppercase">
              {columns.map((c) => <th key={c} className={`px-3 py-2 font-medium ${typeof rows[0][c] === "number" || MONEY_COLUMNS.has(c) ? "text-right" : ""}`}>{title(c)}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index} className="border-b border-line/70 last:border-0">
                {columns.map((c) => (
                  <td key={c} className={`px-3 py-2 ${typeof row[c] === "number" || MONEY_COLUMNS.has(c) ? "num text-right" : ""}`}>
                    {MONEY_COLUMNS.has(c) ? money(row[c]) : (row[c] ?? "—")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {!table.loading && rows.length === 0 && <p className="px-3 py-8 text-center text-muted">No data for this report.</p>}
      </Card>
    </>
  );
}
