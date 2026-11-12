"use client";

import { useEffect, useRef, useState } from "react";
import type { TrendBucket } from "@/lib/types";

export interface ChartSeries {
  key: number;
  label: string;
  /** One value per bucket; zeros included, so a quiet period reads as zero, not a gap. */
  values: number[];
  /** Palette slot 1-8, held by this entity for as long as it is on the chart. */
  slot: number;
}

const PLOT_HEIGHT = 300;
const AXIS_BAND = 30;
const PAD_TOP = 10;
const PAD_LEFT = 54;
const PAD_RIGHT = 18;

/** The validated categorical palette, in the order slots are handed out. */
const PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"];

export const seriesColor = (slot: number) => {
  const index = ((slot - 1) % PALETTE.length + PALETTE.length) % PALETTE.length;
  return `var(--color-series-${index + 1}, ${PALETTE[index]})`;
};

export function parseBucket(label: string): Date {
  const [datePart, timePart] = label.split("T");
  const [year, month, day] = datePart.split("-").map(Number);
  return new Date(year, month - 1, day, timePart ? Number(timePart.slice(0, 2)) : 0);
}

export function tickLabel(label: string, bucket: TrendBucket): string {
  const date = parseBucket(label);
  if (bucket === "hour") return `${String(date.getHours()).padStart(2, "0")}:00`;
  if (bucket === "month") return date.toLocaleDateString("en-GB", { month: "short", year: "2-digit" });
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

export function fullBucketLabel(label: string, bucket: TrendBucket): string {
  const date = parseBucket(label);
  if (bucket === "hour")
    return `${date.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" })}, ${String(date.getHours()).padStart(2, "0")}:00`;
  if (bucket === "month") return date.toLocaleDateString("en-GB", { month: "long", year: "numeric" });
  if (bucket === "week") return `Week of ${date.toLocaleDateString("en-GB", { day: "numeric", month: "short" })}`;
  return date.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}

function niceTicks(max: number): number[] {
  if (max <= 0) return [0, 1];
  const rough = max / 4;
  const exponent = Math.floor(Math.log10(rough));
  const base = 10 ** exponent;
  const normalised = rough / base;
  const step = (normalised <= 1 ? 1 : normalised <= 2 ? 2 : normalised <= 5 ? 5 : 10) * base;
  const ticks: number[] = [];
  for (let value = 0; value < max + step; value += step) ticks.push(Number(value.toFixed(6)));
  return ticks;
}

/**
 * Multi-series time chart. One line per entity in a fixed palette order, a crosshair that
 * snaps to the nearest period and reads out every series at once, and the peak of each
 * series marked — the question these charts get asked is "when was it highest".
 */
export function LineChart({
  buckets,
  series,
  bucket,
  measureLabel,
  formatValue,
  stale,
}: {
  buckets: string[];
  series: ChartSeries[];
  bucket: TrendBucket;
  measureLabel: string;
  formatValue: (value: number) => string;
  stale?: boolean;
}) {
  const wrapper = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(880);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    const element = wrapper.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(360, entry.contentRect.width)));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const count = buckets.length;
  const labelPeaks = series.length <= 4; // direct labels work because they are sparing
  const padRight = labelPeaks ? PAD_RIGHT + 18 : PAD_RIGHT;
  const innerWidth = Math.max(80, width - PAD_LEFT - padRight);
  const height = PAD_TOP + PLOT_HEIGHT + AXIS_BAND;

  const highest = Math.max(0, ...series.flatMap((row) => row.values));
  const ticks = niceTicks(highest);
  const top = ticks[ticks.length - 1];
  const x = (index: number) => PAD_LEFT + (count < 2 ? innerWidth / 2 : (index * innerWidth) / (count - 1));
  const y = (value: number) => PAD_TOP + PLOT_HEIGHT - (value / top) * PLOT_HEIGHT;

  const everyNth = Math.max(1, Math.ceil(count / Math.max(2, Math.floor(innerWidth / 78))));
  // Label every nth period, plus the last one only when it is a full step clear of the
  // one before it — otherwise the two labels collide at the right edge.
  const lastLabelled = Math.floor((count - 1) / everyNth) * everyNth;
  const labelLast = count - 1 - lastLabelled >= everyNth;
  const labelled = (index: number) => index % everyNth === 0 || (index === count - 1 && labelLast);
  const showDots = count <= 24;

  const pointerIndex = (clientX: number) => {
    const box = wrapper.current?.getBoundingClientRect();
    if (!box || count === 0) return null;
    const offset = clientX - box.left - PAD_LEFT;
    return Math.min(count - 1, Math.max(0, Math.round((offset / innerWidth) * (count - 1))));
  };

  const move = (step: number) =>
    setHover((current) => Math.min(count - 1, Math.max(0, (current ?? 0) + step)));

  const readout = hover === null ? null : series.map((row) => ({ ...row, value: row.values[hover] ?? 0 }));

  return (
    <div
      ref={wrapper}
      className={`relative transition-opacity ${stale ? "opacity-60" : ""}`}
      tabIndex={0}
      role="img"
      aria-label={`${measureLabel} per ${bucket} for ${series.map((row) => row.label).join(", ")}. The table view below lists every value.`}
      onKeyDown={(event) => {
        const steps: Record<string, number> = { ArrowRight: 1, ArrowLeft: -1 };
        if (event.key in steps) {
          event.preventDefault();
          move(steps[event.key]);
        } else if (event.key === "Home") setHover(0);
        else if (event.key === "End") setHover(count - 1);
        else if (event.key === "Escape") setHover(null);
      }}
    >
      <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} className="block overflow-visible">
        {/* Gridlines and axis text stay recessive: solid hairlines, muted ink. */}
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={PAD_LEFT} x2={PAD_LEFT + innerWidth} y1={y(tick)} y2={y(tick)} stroke="var(--color-line)" strokeWidth={1} />
            <text x={PAD_LEFT - 10} y={y(tick) + 4} textAnchor="end" className="fill-muted text-[11px] tabular-nums">
              {formatValue(tick)}
            </text>
          </g>
        ))}

        {buckets.map((label, index) =>
          labelled(index) ? (
            <text
              key={label}
              x={x(index)}
              y={PAD_TOP + PLOT_HEIGHT + 19}
              textAnchor={index === 0 ? "start" : index === count - 1 ? "end" : "middle"}
              className="fill-muted text-[11px]"
            >
              {tickLabel(label, bucket)}
            </text>
          ) : null,
        )}

        {hover !== null && (
          <line x1={x(hover)} x2={x(hover)} y1={PAD_TOP} y2={PAD_TOP + PLOT_HEIGHT} stroke="var(--color-muted)" strokeWidth={1} />
        )}

        {series.map((row) => {
          const colour = seriesColor(row.slot);
          const path = row.values.map((value, index) => `${index ? "L" : "M"}${x(index)} ${y(value)}`).join(" ");
          const peakValue = Math.max(...row.values);
          const peakIndex = row.values.indexOf(peakValue);
          return (
            <g key={row.key} style={{ color: colour }}>
              <path d={path} fill="none" stroke="currentColor" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
              {showDots &&
                row.values.map((value, index) => (
                  <circle key={index} cx={x(index)} cy={y(value)} r={3} fill="currentColor" />
                ))}
              {peakValue > 0 && (
                <>
                  {/* The peak is the answer to "when did this sell most", so it is marked and,
                      with few series, labelled — a 2px surface ring keeps overlaps readable. */}
                  <circle cx={x(peakIndex)} cy={y(peakValue)} r={4.5} fill="currentColor" stroke="var(--color-surface)" strokeWidth={2} />
                  {labelPeaks && (
                    <text
                      x={x(peakIndex)}
                      y={y(peakValue) - 10}
                      textAnchor={peakIndex === count - 1 ? "end" : peakIndex === 0 ? "start" : "middle"}
                      className="fill-ink text-[11px] font-semibold tabular-nums"
                    >
                      {formatValue(peakValue)}
                    </text>
                  )}
                </>
              )}
              {hover !== null && (
                <circle cx={x(hover)} cy={y(row.values[hover] ?? 0)} r={4} fill="currentColor" stroke="var(--color-surface)" strokeWidth={2} />
              )}
            </g>
          );
        })}

        <rect
          x={PAD_LEFT - 12}
          y={PAD_TOP}
          width={innerWidth + 24}
          height={PLOT_HEIGHT}
          fill="transparent"
          onPointerMove={(event) => setHover(pointerIndex(event.clientX))}
          onPointerLeave={() => setHover(null)}
        />
      </svg>

      {readout && (
        <div
          className="pointer-events-none absolute top-2 z-10 min-w-40 rounded-md border border-line bg-surface p-2.5 shadow-lg"
          style={x(hover!) > width / 2 ? { right: width - x(hover!) + 14 } : { left: x(hover!) + 14 }}
        >
          <p className="mb-1.5 text-xs text-muted">{fullBucketLabel(buckets[hover!], bucket)}</p>
          <ul className="space-y-1">
            {readout.map((row) => (
              <li key={row.key} className="flex items-baseline gap-2">
                <span aria-hidden className="mt-1.5 h-0.5 w-3 shrink-0 rounded-full" style={{ background: seriesColor(row.slot) }} />
                <span className="num font-semibold">{formatValue(row.value)}</span>
                <span className="truncate text-[13px] text-muted">{row.label}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 border-t border-line pt-3">
        {series.map((row) => {
          const peak = Math.max(...row.values);
          const peakIndex = row.values.indexOf(peak);
          return (
            <li key={row.key} className="flex items-baseline gap-2 text-[13px]">
              <span aria-hidden className="mt-1.5 h-0.5 w-4 shrink-0 rounded-full" style={{ background: seriesColor(row.slot) }} />
              <span className="font-medium">{row.label}</span>
              <span className="text-muted">
                {peak > 0 ? `peak ${formatValue(peak)} · ${fullBucketLabel(buckets[peakIndex], bucket)}` : "no sales in this period"}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
