"use client";

import { useId, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { useChartAnimation } from "@/lib/animation-preference";
import { formatCompactCurrency, formatCurrency, formatPercent } from "@/lib/format";

const DONUT_COLORS = ["#173b73", "#2f65a7", "#4b83d5", "#8fb4e8", "#a6c4f1", "#d9a41a", "#6f83a2", "#c7d5e8"];

type CategoryRow = { category: string; sales: number };

/**
 * Revenue-by-category donut with a live centre value and hover/focus legend
 * cross-highlight, matching the reference interaction. Values come only from
 * the overview API response.
 */
export function RevenueDonut({ rows }: { rows: CategoryRow[] }) {
  const { isAnimationActive, animationDuration, animationEasing } = useChartAnimation();
  const [active, setActive] = useState<number | null>(null);

  const data = useMemo(() => {
    const sorted = rows
      .filter((row) => Number.isFinite(row.sales) && row.sales > 0)
      .sort((a, b) => b.sales - a.sales);
    const top = sorted.slice(0, 7);
    const rest = sorted.slice(7);
    if (rest.length) {
      top.push({ category: "Other", sales: rest.reduce((sum, row) => sum + row.sales, 0) });
    }
    return top;
  }, [rows]);

  const total = data.reduce((sum, row) => sum + row.sales, 0);
  const selected = active !== null ? data[active] : null;

  if (!data.length) {
    return <p className="empty-copy">No category sales were returned for this period.</p>;
  }

  return (
    <div className="donut-layout">
      <div className="donut-chart-wrap">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart accessibilityLayer key={isAnimationActive ? "animated" : "static"}>
            <Pie
              data={data}
              dataKey="sales"
              nameKey="category"
              innerRadius="64%"
              outerRadius="94%"
              paddingAngle={2}
              stroke="#ffffff"
              strokeWidth={2}
              isAnimationActive={isAnimationActive}
              animationDuration={animationDuration}
              animationEasing={animationEasing}
              onMouseEnter={(_: unknown, index: number) => setActive(index)}
              onMouseLeave={() => setActive(null)}
            >
              {data.map((row, index) => (
                <Cell
                  key={row.category}
                  fill={DONUT_COLORS[index % DONUT_COLORS.length]}
                  opacity={active === null || active === index ? 1 : 0.45}
                />
              ))}
            </Pie>
            <Tooltip formatter={(value) => formatCurrency(Number(value))} />
          </PieChart>
        </ResponsiveContainer>
        <div className="donut-center" aria-live="polite">
          <strong>{formatCompactCurrency(selected ? selected.sales : total)}</strong>
          <span>{selected ? selected.category : "Total sales"}</span>
        </div>
      </div>
      <ul className="donut-legend" aria-label="Revenue by category">
        {data.map((row, index) => {
          const share = total ? (row.sales / total) * 100 : 0;
          return (
            <li key={row.category}>
              <button
                type="button"
                className="donut-legend-row"
                data-active={active === index}
                data-dimmed={active !== null && active !== index}
                onMouseEnter={() => setActive(index)}
                onMouseLeave={() => setActive(null)}
                onFocus={() => setActive(index)}
                onBlur={() => setActive(null)}
                aria-label={`${row.category}: ${formatCurrency(row.sales)} (${formatPercent(share)} of sales)`}
              >
                <span className="donut-legend-swatch" style={{ background: DONUT_COLORS[index % DONUT_COLORS.length] }} aria-hidden="true" />
                <span className="donut-legend-name">{row.category}</span>
                <span className="donut-legend-value">{formatCompactCurrency(row.sales)}</span>
                <span className="donut-legend-share">{formatPercent(share)}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/**
 * Semicircular margin gauge drawn as a lightweight SVG. The arc uses a CSS
 * transition so the sweep respects the animation preference without a chart
 * dependency. Value is the real profit-margin fraction from the API.
 */
export function ProfitGauge({ margin }: { margin: number | null | undefined }) {
  const { isAnimationActive } = useChartAnimation();
  const hasValue = typeof margin === "number" && Number.isFinite(margin);
  const pct = hasValue ? Math.max(0, Math.min(100, margin * 100)) : 0;
  const offset = 100 - pct;
  const remaining = 100 - pct;

  return (
    <div className="gauge-layout">
      <div className="gauge-chart" role="img" aria-label={hasValue ? `Profit margin ${formatPercent(pct)}` : "Profit margin unavailable"}>
        <svg viewBox="0 0 200 116" focusable="false" aria-hidden="true">
          <path
            className="gauge-track"
            d="M 20 100 A 80 80 0 0 1 180 100"
            fill="none"
            strokeWidth={16}
            strokeLinecap="round"
            pathLength={100}
          />
          <path
            className="gauge-value"
            d="M 20 100 A 80 80 0 0 1 180 100"
            fill="none"
            strokeWidth={16}
            strokeLinecap="round"
            pathLength={100}
            strokeDasharray={100}
            strokeDashoffset={offset}
            data-animate={isAnimationActive ? "true" : "false"}
            style={{ transitionDuration: isAnimationActive ? "900ms" : "0ms" }}
          />
        </svg>
        <div className="gauge-center">
          <strong>{hasValue ? formatPercent(pct) : "—"}</strong>
          <span>Profit margin</span>
        </div>
      </div>
      <div className="gauge-legend" aria-hidden="true">
        <span><i />Margin {hasValue ? formatPercent(pct) : "—"}</span>
        <span><i />Remaining {hasValue ? formatPercent(remaining) : "—"}</span>
      </div>
    </div>
  );
}

/**
 * Small area sparkline for KPI cards. Only rendered when the API returns at
 * least two monthly points, so it never invents a trend.
 */
export function KpiSparkline({
  data,
  dataKey,
  variant = "default",
}: {
  data: { date: string; sales: number; profit: number }[];
  dataKey: "sales" | "profit";
  variant?: "default" | "emphasis";
}) {
  const { isAnimationActive, animationDuration, animationEasing } = useChartAnimation();
  const gradientId = useId().replace(/:/g, "");
  const series = data.filter((row) => Number.isFinite(row[dataKey]));
  if (series.length < 2) return null;
  const stroke = variant === "emphasis" ? "#d7e6fb" : "#4b83d5";
  const fill = variant === "emphasis" ? "#ffffff" : "#4b83d5";

  return (
    <div className="kpi-sparkline" aria-hidden="true">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart key={isAnimationActive ? "animated" : "static"} data={series} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={`kpi-spark-${gradientId}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={fill} stopOpacity={variant === "emphasis" ? 0.35 : 0.28} />
              <stop offset="100%" stopColor={fill} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey={dataKey}
            stroke={stroke}
            strokeWidth={1.6}
            fill={`url(#kpi-spark-${gradientId})`}
            isAnimationActive={isAnimationActive}
            animationDuration={animationDuration}
            animationEasing={animationEasing}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
