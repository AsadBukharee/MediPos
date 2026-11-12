"use client";

import Link from "next/link";
import { useState } from "react";
import { type ChartSeries, LineChart, fullBucketLabel, seriesColor } from "@/components/line-chart";
import { type PickedProduct, ProductPicker } from "@/components/product-picker";
import { Button, Card, Input, Notice, PageHeader, Select, Tabs } from "@/components/ui";
import { download } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { money, qty, today } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { SalesTrend, TrendBucket } from "@/lib/types";

interface Picked extends PickedProduct {
  /** Palette slot, kept for as long as the medicine is on the chart. */
  slot: number;
}

const MAX_SERIES = 8;
const BUCKETS: [TrendBucket, string][] = [
  ["hour", "By hour"],
  ["day", "By day"],
  ["week", "By week"],
  ["month", "By month"],
];

function shift(days: number) {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString().slice(0, 10);
}

const PRESETS: [string, string, TrendBucket][] = [
  ["Last 7 days", shift(6), "day"],
  ["Last 30 days", shift(29), "day"],
  ["Last 90 days", shift(89), "week"],
  ["Last 12 months", shift(364), "month"],
];

export default function SalesTrendsPage() {
  const { user } = useAuth();
  const [picked, setPicked] = useState<Picked[]>([]);
  const [from, setFrom] = useState(shift(29));
  const [to, setTo] = useState(today);
  const [bucket, setBucket] = useState<TrendBucket>("day");
  const [measure, setMeasure] = useState<"quantity" | "revenue">("quantity");
  const [view, setView] = useState<"chart" | "table">("chart");
  const [consolidated, setConsolidated] = useState(false);

  // A medicine keeps its colour while it is on the chart: removing one never repaints the rest.
  const choose = (next: PickedProduct[]) => {
    const held = new Map(picked.map((item) => [item.id, item.slot]));
    const used = new Set(next.map((item) => held.get(item.id)).filter((slot): slot is number => Boolean(slot)));
    setPicked(
      next.map((item) => {
        const existing = held.get(item.id);
        if (existing) return { ...item, slot: existing };
        let slot = 1;
        while (used.has(slot)) slot += 1;
        used.add(slot);
        return { ...item, slot };
      }),
    );
  };

  const ids = picked.map((item) => item.id);
  const params = {
    products: ids.join(","),
    bucket,
    date_from: from,
    date_to: to,
    consolidated: consolidated ? 1 : undefined,
  };
  const trend = useApi<SalesTrend>(ids.length ? "/reports/sales/trend/" : null, params);
  const data = trend.data;

  const slotOf = new Map(picked.map((item) => [item.id, item.slot]));
  const series: ChartSeries[] = (data?.series ?? [])
    .filter((row) => slotOf.has(row.product))
    .map((row) => ({
      key: row.product,
      label: row.label,
      slot: slotOf.get(row.product) ?? 1,
      values: measure === "quantity" ? row.quantity : row.revenue.map(Number),
    }));
  const format = measure === "quantity" ? (value: number) => qty(value) : (value: number) => money(value);
  const measureLabel = measure === "quantity" ? "Units sold" : "Revenue";

  return (
    <>
      <PageHeader
        title="Sales trends"
        subtitle="Pick up to eight medicines and see when each one sells most."
      >
        <Link href="/reports" className="text-[13px] font-medium text-brand hover:underline">
          Report tables
        </Link>
      </PageHeader>

      {/* One filter row above everything it scopes, date range first. */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Select
          aria-label="Period"
          className="w-40"
          value={PRESETS.find(([, start]) => start === from && to === today())?.[0] ?? "custom"}
          onChange={(event) => {
            const preset = PRESETS.find(([label]) => label === event.target.value);
            if (!preset) return;
            setFrom(preset[1]);
            setTo(today());
            setBucket(preset[2]);
          }}
        >
          {PRESETS.map(([label]) => (
            <option key={label} value={label}>
              {label}
            </option>
          ))}
          <option value="custom">Custom range</option>
        </Select>
        <Input type="date" aria-label="From" value={from} max={to} onChange={(event) => setFrom(event.target.value)} className="w-40" />
        <Input type="date" aria-label="To" value={to} min={from} onChange={(event) => setTo(event.target.value)} className="w-40" />
        <Select
          aria-label="Group by"
          value={bucket}
          onChange={(event) => {
            const next = event.target.value as TrendBucket;
            setBucket(next);
            // An hour-by-hour view only makes sense over a day or two, so narrow the range
            // instead of letting the request come back as an error.
            if (next === "hour" && new Date(to).getTime() - new Date(from).getTime() > 2 * 86_400_000) setFrom(to);
          }}
          className="w-36"
        >
          {BUCKETS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
        <Select aria-label="Measure" value={measure} onChange={(event) => setMeasure(event.target.value as "quantity" | "revenue")} className="w-36">
          <option value="quantity">Units sold</option>
          <option value="revenue">Revenue</option>
        </Select>
        <ProductPicker selected={picked} onChange={choose} max={MAX_SERIES} />
        {(user?.branches.length ?? 0) > 1 && (
          <label className="flex items-center gap-1.5 text-[13px]">
            <input type="checkbox" checked={consolidated} onChange={(event) => setConsolidated(event.target.checked)} /> All my branches
          </label>
        )}
        {ids.length > 0 && (
          <Button variant="secondary" onClick={() => download("/reports/sales/trend/", params, "sales-trend.csv")}>
            Export CSV
          </Button>
        )}
      </div>

      {picked.length > 0 && (
        <ul className="mb-3 flex flex-wrap gap-2">
          {picked.map((item) => (
            <li key={item.id} className="flex items-center gap-2 rounded-full border border-line bg-surface py-1 pr-1.5 pl-2.5 text-[13px]">
              <span aria-hidden className="size-2.5 rounded-full" style={{ background: seriesColor(item.slot) }} />
              {item.label}
              <button
                aria-label={`Remove ${item.label}`}
                onClick={() => choose(picked.filter((other) => other.id !== item.id))}
                className="rounded-full px-1 text-muted hover:bg-canvas hover:text-danger"
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}

      <Notice>{trend.error}</Notice>

      {ids.length === 0 ? (
        <Card className="px-4 py-16 text-center">
          <p className="font-medium">Choose a medicine to see its sales over time.</p>
          <p className="mt-1 text-muted">
            Use <span className="font-medium text-ink">Choose medicines</span> above — search by name, generic name or SKU, and tick
            up to {MAX_SERIES}. Each one gets its own coloured line.
          </p>
        </Card>
      ) : (
        <Card className="p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="font-semibold">{measureLabel} per {bucket}</h2>
              <p className="text-[13px] text-muted">
                {series.length} medicine{series.length === 1 ? "" : "s"}
                {data ? ` · ${data.buckets.length} ${bucket}${data.buckets.length === 1 ? "" : "s"}` : ""}
                {measure === "quantity" ? " · base units (tablets, capsules, ml)" : ""}
              </p>
            </div>
            <Tabs value={view} onChange={setView} options={[["chart", "Chart"], ["table", "Table"]]} />
          </div>

          {!data ? (
            <p className="py-20 text-center text-muted">Loading…</p>
          ) : view === "chart" ? (
            <LineChart
              buckets={data.buckets}
              series={series}
              bucket={data.bucket}
              measureLabel={measureLabel}
              formatValue={format}
              stale={trend.loading}
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-line text-[13px] text-muted">
                    <th className="px-2 py-2 text-xs font-medium tracking-wide uppercase">Period</th>
                    {series.map((row) => (
                      <th key={row.key} className="px-2 py-2 text-right font-medium">
                        <span aria-hidden className="mr-1.5 inline-block h-0.5 w-3 align-middle" style={{ background: seriesColor(row.slot) }} />
                        {row.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.buckets.map((label, index) => (
                    <tr key={label} className="border-b border-line/70 last:border-0">
                      <td className="px-2 py-1.5">{fullBucketLabel(label, data.bucket)}</td>
                      {series.map((row) => (
                        <td key={row.key} className="num px-2 py-1.5 text-right">
                          {format(row.values[index] ?? 0)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t border-line font-semibold">
                    <td className="px-2 py-2">Total</td>
                    {series.map((row) => (
                      <td key={row.key} className="num px-2 py-2 text-right">
                        {format(row.values.reduce((sum, value) => sum + value, 0))}
                      </td>
                    ))}
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
        </Card>
      )}
    </>
  );
}
