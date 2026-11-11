"use client";

import Link from "next/link";
import { Card, Notice, PageHeader, Stat } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { money, qty } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Dashboard } from "@/lib/types";

export default function DashboardPage() {
  const { branch } = useAuth();
  const { data, error, loading } = useApi<Dashboard>("/reports/dashboard/");

  if (error) return <Notice>{error}</Notice>;
  if (loading || !data) return <p className="text-muted">Loading…</p>;
  const peak = Math.max(1, ...data.sales_chart.map((d) => Number(d.total)));

  return (
    <>
      <PageHeader title="Dashboard" subtitle={branch?.name} />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Today's sales" value={money(data.today_sales)} hint={`${data.today_invoices} invoice(s)`} />
        <Stat label="Revenue this month" value={money(data.month_revenue)} />
        <Stat label="Gross profit this month" value={money(data.month_gross_profit)} tone="ok" />
        <Stat label="Purchases this month" value={money(data.month_purchases)} />
        <Stat label="Stock value (at cost)" value={money(data.stock_value)} />
        <Stat label="Owed to suppliers" value={money(data.supplier_payables)} />
        <Stat label="Owed by customers" value={money(data.customer_receivables)} />
        <Card className="grid grid-cols-2 gap-x-4 gap-y-1 p-4 text-[13px]">
          <Link href="/inventory?state=low" className="text-muted hover:text-ink">Low stock</Link>
          <span className="num text-right font-semibold text-warn">{data.low_stock_count}</span>
          <Link href="/inventory?state=out" className="text-muted hover:text-ink">Out of stock</Link>
          <span className="num text-right font-semibold text-danger">{data.out_of_stock_count}</span>
          <Link href="/inventory?tab=expiry" className="text-muted hover:text-ink">Expiring in 30 days</Link>
          <span className="num text-right font-semibold text-warn">{data.near_expiry_count}</span>
          <Link href="/inventory?tab=expiry" className="text-muted hover:text-ink">Expired batches</Link>
          <span className="num text-right font-semibold text-danger">{data.expired_count}</span>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[2fr_1fr]">
        <Card className="p-4">
          <h2 className="font-semibold">Sales, last 14 days</h2>
          {data.sales_chart.length === 0 ? (
            <p className="py-10 text-center text-muted">No sales in this period.</p>
          ) : (
            <div className="mt-4 flex h-48 items-end gap-1.5" role="img" aria-label="Daily sales bar chart">
              {data.sales_chart.map((day) => (
                <div key={day.label} className="group flex h-full flex-1 flex-col justify-end" title={`${day.label}: ${money(day.total)} · profit ${money(day.profit)}`}>
                  <div className="rounded-t bg-brand/85 group-hover:bg-brand-strong" style={{ height: `${Math.max(2, (Number(day.total) / peak) * 100)}%` }} />
                  <span className="mt-1 text-center text-[10px] text-muted">{day.label.slice(8)}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
        <Card className="p-4">
          <h2 className="font-semibold">Top medicines this month</h2>
          <ul className="mt-2 divide-y divide-line/70">
            {data.top_products.map((row) => (
              <li key={row.key} className="flex items-center justify-between py-2">
                <span className="truncate pr-3">{row.label}</span>
                <span className="num shrink-0 text-muted">
                  {qty(row.quantity)} · <span className="font-medium text-ink">{money(row.revenue)}</span>
                </span>
              </li>
            ))}
            {data.top_products.length === 0 && <li className="py-6 text-center text-muted">No sales yet.</li>}
          </ul>
        </Card>
      </div>
    </>
  );
}
