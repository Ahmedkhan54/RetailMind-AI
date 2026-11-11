"use client";

/**
 * Reusable advanced visualisation primitives for RetailMind.
 *
 * Every component receives already-aggregated rows from the Python visuals
 * endpoint and renders them without inventing values. Recharts is reused for
 * standard charts; small SVG/CSS primitives cover waterfall, ribbon, box plot,
 * heatmap, and decomposition views. Animation always follows the shared
 * `useChartAnimation()` preference (Problem 62).
 */

import { useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  Treemap,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { useChartAnimation } from "@/lib/animation-preference";
import { formatCompactCurrency, formatCurrency, formatNumber, formatPercent } from "@/lib/format";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export const VISUAL_COLORS = [
  "#173b73",
  "#2f65a7",
  "#4b83d5",
  "#8fb4e8",
  "#d9a41a",
  "#6f83a2",
  "#c7d5e8",
  "#a6c4f1",
];

type Row = Record<string, unknown>;
type SelectHandler = (label: string) => void;

export function ChartEmpty({ message = "No matching records for this chart." }: { message?: string }) {
  return <div className="feature-chart-blank"><span>{message}</span></div>;
}

function numeric(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function text(value: unknown, fallback = "Unmapped"): string {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function shortLabel(value: string, limit = 18): string {
  return value.length > limit ? `${value.slice(0, limit - 1)}…` : value;
}

function compact(value: number): string {
  return new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

export type ComparisonProps = {
  rows: Row[];
  labelKey: string;
  primaryKey?: string;
  secondaryKey?: string;
  primaryName?: string;
  secondaryName?: string;
  stacked?: boolean;
  horizontal?: boolean;
  height?: number;
  onSelect?: SelectHandler;
};

/** Clustered or stacked bar comparison of two real measures. */
export function ComparisonBarChart({
  rows,
  labelKey,
  primaryKey = "sales",
  secondaryKey = "profit",
  primaryName = "Sales",
  secondaryName = "Profit",
  stacked = false,
  horizontal = false,
  height = 280,
  onSelect,
}: ComparisonProps) {
  const animation = useChartAnimation();
  const data = useMemo(
    () => rows.map((row) => ({
      label: text(row[labelKey]),
      primary: numeric(row[primaryKey]),
      secondary: secondaryKey ? numeric(row[secondaryKey]) : 0,
    })),
    [rows, labelKey, primaryKey, secondaryKey],
  );
  if (!data.length) return <ChartEmpty />;
  const handleSelect = onSelect
    ? (entry: unknown) => {
        const payload = (entry as { payload?: { label?: string } })?.payload;
        if (payload?.label) onSelect(payload.label);
      }
    : undefined;

  return (
    <div className="visual-chart" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          accessibilityLayer
          key={animation.isAnimationActive ? "animated" : "static"}
          data={data}
          layout={horizontal ? "vertical" : "horizontal"}
          margin={{ top: 10, right: 12, bottom: 4, left: horizontal ? 8 : 0 }}
        >
          <CartesianGrid stroke="#edf0f5" strokeDasharray="3 4" vertical={horizontal} horizontal={!horizontal} />
          {horizontal ? (
            <>
              <XAxis type="number" tickLine={false} axisLine={false} tick={{ fill: "#8993a2", fontSize: 9 }} tickFormatter={compact} />
              <YAxis type="category" dataKey="label" width={106} tickLine={false} axisLine={false} tick={{ fill: "#8993a2", fontSize: 9 }} tickFormatter={(value: string) => shortLabel(value, 16)} />
            </>
          ) : (
            <>
              <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: "#8993a2", fontSize: 9 }} tickFormatter={(value: string) => shortLabel(value, 13)} interval={0} angle={data.length > 6 ? -18 : 0} textAnchor={data.length > 6 ? "end" : "middle"} height={data.length > 6 ? 52 : 30} />
              <YAxis tickLine={false} axisLine={false} tick={{ fill: "#8993a2", fontSize: 9 }} tickFormatter={compact} />
            </>
          )}
          <Tooltip formatter={(value) => formatCurrency(Number(value))} cursor={{ fill: "#f4f7fb" }} />
          <Legend verticalAlign="top" height={28} iconType="circle" wrapperStyle={{ fontSize: 11 }} />
          <Bar dataKey="primary" name={primaryName} stackId={stacked ? "measures" : undefined} fill={VISUAL_COLORS[1]} radius={stacked ? 0 : [4, 4, 0, 0]} barSize={stacked ? 18 : 12} onClick={handleSelect} cursor={onSelect ? "pointer" : undefined} isAnimationActive={animation.isAnimationActive} animationDuration={animation.animationDuration} animationEasing={animation.animationEasing} />
          {secondaryKey ? (
            <Bar dataKey="secondary" name={secondaryName} stackId={stacked ? "measures" : undefined} fill={VISUAL_COLORS[3]} radius={stacked ? [4, 4, 0, 0] : [4, 4, 0, 0]} barSize={stacked ? 18 : 12} onClick={handleSelect} cursor={onSelect ? "pointer" : undefined} isAnimationActive={animation.isAnimationActive} animationDuration={animation.animationDuration} animationEasing={animation.animationEasing} animationBegin={90} />
          ) : null}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export type TrendProps = {
  rows: Row[];
  mode: "line" | "area" | "combo";
  primaryKey?: string;
  secondaryKey?: string;
  primaryName?: string;
  secondaryName?: string;
  height?: number;
};

/** Line, area, or combo trend over the monthly date field. */
export function TrendChart({
  rows,
  mode,
  primaryKey = "sales",
  secondaryKey = "profit",
  primaryName = "Sales",
  secondaryName = "Profit",
  height = 280,
}: TrendProps) {
  const animation = useChartAnimation();
  const data = useMemo(
    () => rows
      .map((row) => ({
        label: text(row.date ?? row.label, ""),
        primary: numeric(row[primaryKey]),
        secondary: numeric(row[secondaryKey]),
      }))
      .filter((row) => row.label),
    [rows, primaryKey, secondaryKey],
  );
  if (!data.length) return <ChartEmpty />;
  const dateTick = (value: string) => {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString("en-IN", { month: "short", year: "2-digit" });
  };
  const common = {
    accessibilityLayer: true,
    data,
    margin: { top: 12, right: 12, bottom: 4, left: 0 },
  };
  const axes = (
    <>
      <CartesianGrid stroke="#edf0f5" strokeDasharray="3 4" vertical={false} />
      <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: "#8993a2", fontSize: 9 }} tickFormatter={dateTick} minTickGap={20} />
      <YAxis tickLine={false} axisLine={false} tick={{ fill: "#8993a2", fontSize: 9 }} tickFormatter={compact} />
      <Tooltip formatter={(value) => formatCurrency(Number(value))} labelFormatter={(value) => {
        const date = new Date(String(value));
        return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleDateString("en-IN", { month: "long", year: "numeric" });
      }} />
      <Legend verticalAlign="top" height={28} iconType="circle" wrapperStyle={{ fontSize: 11 }} />
    </>
  );
  const animationKey = animation.isAnimationActive ? "animated" : "static";

  if (mode === "combo") {
    return (
      <div className="visual-chart" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart key={animationKey} {...common}>
            {axes}
            <Bar dataKey="primary" name={primaryName} fill={VISUAL_COLORS[1]} radius={[4, 4, 0, 0]} barSize={16} isAnimationActive={animation.isAnimationActive} animationDuration={animation.animationDuration} animationEasing={animation.animationEasing} />
            <Line type="monotone" dataKey="secondary" name={secondaryName} stroke={VISUAL_COLORS[4]} strokeWidth={2.2} dot={false} isAnimationActive={animation.isAnimationActive} animationDuration={animation.animationDuration} animationEasing={animation.animationEasing} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    );
  }
  if (mode === "line") {
    return (
      <div className="visual-chart" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart key={animationKey} {...common}>
            {axes}
            <Line type="monotone" dataKey="primary" name={primaryName} stroke={VISUAL_COLORS[1]} strokeWidth={2.3} dot={false} isAnimationActive={animation.isAnimationActive} animationDuration={animation.animationDuration} animationEasing={animation.animationEasing} />
            <Line type="monotone" dataKey="secondary" name={secondaryName} stroke={VISUAL_COLORS[4]} strokeWidth={1.8} strokeDasharray="5 4" dot={false} isAnimationActive={animation.isAnimationActive} animationDuration={animation.animationDuration} animationEasing={animation.animationEasing} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    );
  }
  const gradientId = `visual-area-${primaryKey}`;
  return (
    <div className="visual-chart" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart key={animationKey} {...common}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={VISUAL_COLORS[1]} stopOpacity={0.28} />
              <stop offset="95%" stopColor={VISUAL_COLORS[1]} stopOpacity={0} />
            </linearGradient>
          </defs>
          {axes}
          <Area type="monotone" dataKey="primary" name={primaryName} stroke={VISUAL_COLORS[1]} strokeWidth={2.3} fill={`url(#${gradientId})`} isAnimationActive={animation.isAnimationActive} animationDuration={animation.animationDuration} animationEasing={animation.animationEasing} />
          <Area type="monotone" dataKey="secondary" name={secondaryName} stroke={VISUAL_COLORS[4]} strokeWidth={1.6} strokeDasharray="5 4" fill="transparent" isAnimationActive={animation.isAnimationActive} animationDuration={animation.animationDuration} animationEasing={animation.animationEasing} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export type ShareDatum = { label: string; value: number };
export type ShareDonutProps = {
  rows: ShareDatum[];
  centerLabel?: string;
  height?: number;
  onSelect?: SelectHandler;
};

/** Generic pie/donut with a live centre value and clickable legend. */
export function ShareDonut({ rows, centerLabel = "Total", height = 260, onSelect }: ShareDonutProps) {
  const animation = useChartAnimation();
  const [active, setActive] = useState<number | null>(null);
  const data = useMemo(() => rows.filter((row) => Number.isFinite(row.value) && row.value > 0).slice(0, 9), [rows]);
  const total = data.reduce((sum, row) => sum + row.value, 0);
  if (!data.length) return <ChartEmpty />;

  return (
    <div className="visual-donut">
      <div className="visual-donut-chart" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart accessibilityLayer key={animation.isAnimationActive ? "animated" : "static"}>
            <Pie
              data={data}
              dataKey="value"
              nameKey="label"
              innerRadius="58%"
              outerRadius="90%"
              paddingAngle={2}
              stroke="#ffffff"
              strokeWidth={2}
              isAnimationActive={animation.isAnimationActive}
              animationDuration={animation.animationDuration}
              animationEasing={animation.animationEasing}
              onMouseEnter={(_: unknown, index: number) => setActive(index)}
              onMouseLeave={() => setActive(null)}
            >
              {data.map((row, index) => (
                <Cell key={row.label} fill={VISUAL_COLORS[index % VISUAL_COLORS.length]} opacity={active === null || active === index ? 1 : 0.45} />
              ))}
            </Pie>
            <Tooltip formatter={(value) => formatCurrency(Number(value))} />
          </PieChart>
        </ResponsiveContainer>
        <div className="visual-donut-center">
          <strong>{formatCompactCurrency(active === null ? total : data[active].value)}</strong>
          <span>{active === null ? centerLabel : data[active].label}</span>
        </div>
      </div>
      <ul className="visual-donut-legend">
        {data.map((row, index) => (
          <li key={row.label}>
            <button
              type="button"
              className="visual-legend-button"
              onMouseEnter={() => setActive(index)}
              onMouseLeave={() => setActive(null)}
              onFocus={() => setActive(index)}
              onBlur={() => setActive(null)}
              onClick={() => onSelect?.(row.label)}
              aria-label={`${row.label}: ${formatCurrency(row.value)}`}
            >
              <i style={{ background: VISUAL_COLORS[index % VISUAL_COLORS.length] }} aria-hidden="true" />
              <span>{row.label}</span>
              <strong>{formatCompactCurrency(row.value)}</strong>
              <em>{formatPercent(total ? (row.value / total) * 100 : 0)}</em>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export type TreemapProps = {
  rows: Row[];
  labelKey: string;
  valueKey?: string;
  height?: number;
  onSelect?: SelectHandler;
};

/** Treemap of product or category contribution using real sales. */
export function ContributionTreemap({ rows, labelKey, valueKey = "sales", height = 300, onSelect }: TreemapProps) {
  const [active, setActive] = useState<string | null>(null);
  const data = useMemo(
    () => rows
      .map((row) => ({ name: text(row[labelKey]), size: numeric(row[valueKey]), raw: row }))
      .filter((row) => row.size > 0)
      .slice(0, 40),
    [rows, labelKey, valueKey],
  );
  if (!data.length) return <ChartEmpty />;

  return (
    <div className="visual-chart" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <Treemap
          data={data}
          dataKey="size"
          nameKey="name"
          aspectRatio={4 / 3}
          stroke="#ffffff"
          fill={VISUAL_COLORS[1]}
          onClick={(entry: unknown) => {
            const name = (entry as { name?: string })?.name;
            if (name) onSelect?.(name);
          }}
        >
          <Tooltip formatter={(value) => formatCurrency(Number(value))} />
          {data.map((row, index) => (
            <Cell
              key={row.name}
              fill={VISUAL_COLORS[index % VISUAL_COLORS.length]}
              opacity={active === null || active === row.name ? 1 : 0.65}
              onMouseEnter={() => setActive(row.name)}
              onMouseLeave={() => setActive(null)}
            />
          ))}
        </Treemap>
      </ResponsiveContainer>
    </div>
  );
}

export type ScatterProps = {
  rows: Row[];
  xKey?: string;
  yKey?: string;
  sizeKey?: string;
  colorKey?: string;
  height?: number;
  onSelect?: SelectHandler;
};

/** Scatter/bubble chart for sales versus profit, sized by sales. */
export function SalesProfitScatter({
  rows,
  xKey = "sales",
  yKey = "profit",
  sizeKey = "sales",
  colorKey = "category",
  height = 320,
  onSelect,
}: ScatterProps) {
  const animation = useChartAnimation();
  const data = useMemo(
    () => rows
      .map((row) => ({
        x: numeric(row[xKey]),
        y: numeric(row[yKey]),
        z: Math.abs(numeric(row[sizeKey])),
        category: text(row[colorKey]),
        label: text(row.product_name ?? row.city ?? row.category),
      }))
      .filter((row) => row.x !== 0 || row.y !== 0),
    [rows, xKey, yKey, sizeKey, colorKey],
  );
  const categories = useMemo(() => Array.from(new Set(data.map((row) => row.category))).slice(0, 8), [data]);
  const [active, setActive] = useState<string | null>(null);
  if (!data.length) return <ChartEmpty />;

  return (
    <div className="visual-chart" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart key={animation.isAnimationActive ? "animated" : "static"} margin={{ top: 16, right: 18, bottom: 8, left: 4 }} accessibilityLayer>
          <CartesianGrid stroke="#edf0f5" strokeDasharray="3 4" />
          <XAxis type="number" dataKey="x" name="Sales" tickLine={false} axisLine={false} tick={{ fill: "#8993a2", fontSize: 9 }} tickFormatter={compact} />
          <YAxis type="number" dataKey="y" name="Profit" tickLine={false} axisLine={false} tick={{ fill: "#8993a2", fontSize: 9 }} tickFormatter={compact} />
          <ZAxis type="number" dataKey="z" range={[50, 420]} />
          <ReferenceLine y={0} stroke="#c3ccd9" strokeDasharray="4 4" />
          <Tooltip
            cursor={{ strokeDasharray: "3 3" }}
            formatter={(value, name) => [formatCurrency(Number(value)), String(name)]}
            labelFormatter={() => ""}
          />
          <Legend verticalAlign="top" height={26} iconType="circle" wrapperStyle={{ fontSize: 11 }} />
          {categories.map((category, index) => (
            <Scatter
              key={category}
              name={category}
              data={data.filter((row) => row.category === category)}
              fill={VISUAL_COLORS[index % VISUAL_COLORS.length]}
              fillOpacity={active === null || active === category ? 0.78 : 0.25}
              onClick={(entry: unknown) => {
                const label = (entry as { label?: string })?.label;
                if (label) onSelect?.(label);
              }}
              onMouseEnter={() => setActive(category)}
              onMouseLeave={() => setActive(null)}
              isAnimationActive={animation.isAnimationActive}
              animationDuration={animation.animationDuration}
              animationEasing={animation.animationEasing}
            />
          ))}
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}

export type WaterfallRow = {
  label: string;
  value: number;
  start: number;
  end: number;
  type: "increase" | "decrease" | "total";
};

/** Waterfall of signed profit contributions with a real cumulative total. */
export function WaterfallChart({ rows, height = 300, onSelect }: { rows: WaterfallRow[]; height?: number; onSelect?: SelectHandler }) {
  if (!rows.length) return <ChartEmpty />;
  const values = rows.flatMap((row) => [row.start, row.end, 0]);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;

  return (
    <div className="waterfall" style={{ height }}>
      <div className="waterfall-plot" role="img" aria-label="Profit contribution waterfall">
        {rows.map((row, index) => {
          const top = ((max - Math.max(row.start, row.end)) / span) * 100;
          const size = (Math.abs(row.end - row.start) / span) * 100;
          return (
            <button
              type="button"
              key={row.label}
              className={`waterfall-column waterfall-${row.type}`}
              style={{ top: `${top}%`, height: `${Math.max(size, 0.6)}%`, left: `${(index / rows.length) * 100 + 0.6}%`, width: `${Math.max(100 / rows.length - 2.2, 6)}%` }}
              title={`${row.label}: ${formatCurrency(row.value)}`}
              onClick={() => row.type !== "total" && onSelect?.(row.label)}
              disabled={!onSelect || row.type === "total"}
            >
              <span className="waterfall-value">{formatCompactCurrency(row.value)}</span>
              <span className="waterfall-label">{shortLabel(row.label, 12)}</span>
            </button>
          );
        })}
      </div>
      <div className="waterfall-baseline" aria-hidden="true" />
    </div>
  );
}

export type FunnelStage = { stage: string; value: number; share: number; products?: number };

/** Observed product sales concentration funnel. */
export function FunnelChart({ stages }: { stages: FunnelStage[] }) {
  if (!stages.length) return <ChartEmpty />;
  return (
    <div className="visual-funnel" role="list" aria-label="Sales concentration funnel">
      {stages.map((stage, index) => (
        <div className="visual-funnel-stage" key={stage.stage} role="listitem">
          <div
            className="visual-funnel-bar"
            style={{ width: `${Math.max(stage.share * 100, 16)}%`, background: VISUAL_COLORS[index % VISUAL_COLORS.length] }}
            title={`${stage.stage}: ${formatCurrency(stage.value)} (${formatPercent(stage.share * 100)})`}
          >
            <span>{shortLabel(stage.stage, 20)}</span>
            <strong>{formatCompactCurrency(stage.value)}</strong>
          </div>
          <em>{formatPercent(stage.share * 100)} of product sales</em>
        </div>
      ))}
    </div>
  );
}

/** Semicircular gauge for a real percentage measure. */
export function GaugeMeter({ value, label, detail, max = 100 }: { value: number | null; label: string; detail?: string; max?: number }) {
  const animation = useChartAnimation();
  const hasValue = typeof value === "number" && Number.isFinite(value);
  const pct = hasValue ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  return (
    <div className="gauge-layout visual-gauge">
      <div className="gauge-chart" role="img" aria-label={hasValue ? `${label} ${formatPercent(pct)}` : `${label} unavailable`}>
        <svg viewBox="0 0 200 116" focusable="false" aria-hidden="true">
          <path className="gauge-track" d="M 20 100 A 80 80 0 0 1 180 100" fill="none" strokeWidth={16} strokeLinecap="round" pathLength={100} />
          <path
            className="gauge-value"
            d="M 20 100 A 80 80 0 0 1 180 100"
            fill="none"
            strokeWidth={16}
            strokeLinecap="round"
            pathLength={100}
            strokeDasharray={100}
            strokeDashoffset={100 - pct}
            data-animate={animation.isAnimationActive ? "true" : "false"}
            style={{ transitionDuration: animation.isAnimationActive ? "900ms" : "0ms" }}
          />
        </svg>
        <div className="gauge-center">
          <strong>{hasValue ? formatPercent(pct) : "—"}</strong>
          <span>{label}</span>
          {detail ? <small>{detail}</small> : null}
        </div>
      </div>
    </div>
  );
}

type RibbonPoint = { date: string; label: string; sales: number };

/** Month-by-category ribbon (alluvial-style share bands). */
export function CategoryRibbon({ rows, height = 300, onSelect }: { rows: RibbonPoint[]; height?: number; onSelect?: SelectHandler }) {
  const [active, setActive] = useState<string | null>(null);
  const model = useMemo(() => {
    const dates = Array.from(new Set(rows.map((row) => row.date))).sort();
    const categories = Array.from(new Set(rows.map((row) => row.label)));
    const totals = new Map<string, number>();
    for (const row of rows) totals.set(row.label, (totals.get(row.label) ?? 0) + row.sales);
    categories.sort((a, b) => (totals.get(b) ?? 0) - (totals.get(a) ?? 0));
    const kept = categories.slice(0, 7);
    const byDate = new Map<string, Map<string, number>>();
    for (const date of dates) byDate.set(date, new Map());
    for (const row of rows) {
      if (!kept.includes(row.label)) continue;
      const bucket = byDate.get(row.date);
      if (bucket) bucket.set(row.label, (bucket.get(row.label) ?? 0) + row.sales);
    }
    const bands = kept.map((label) => ({ label, points: [] as { x: number; lower: number; upper: number }[] }));
    dates.forEach((date, index) => {
      const bucket = byDate.get(date) ?? new Map<string, number>();
      const total = Array.from(bucket.values()).reduce((sum, value) => sum + value, 0) || 1;
      let cumulative = 0;
      const x = dates.length > 1 ? (index / (dates.length - 1)) * 100 : 50;
      for (const band of bands) {
        const share = (bucket.get(band.label) ?? 0) / total;
        const lower = cumulative;
        cumulative += share;
        band.points.push({ x, lower: lower * 100, upper: cumulative * 100 });
      }
    });
    return { dates, bands };
  }, [rows]);

  if (!model.bands.length || !model.dates.length) return <ChartEmpty />;
  return (
    <div className="visual-ribbon" style={{ height }}>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Category share ribbon over time">
        {model.bands.map((band, index) => {
          const top = band.points.map((point) => `${point.x},${100 - point.upper}`).join(" L ");
          const bottom = [...band.points].reverse().map((point) => `${point.x},${100 - point.lower}`).join(" L ");
          return (
            <path
              key={band.label}
              d={`M ${top} L ${bottom} Z`}
              fill={VISUAL_COLORS[index % VISUAL_COLORS.length]}
              opacity={active === null || active === band.label ? 0.82 : 0.25}
              onMouseEnter={() => setActive(band.label)}
              onMouseLeave={() => setActive(null)}
              onClick={() => onSelect?.(band.label)}
              style={{ cursor: onSelect ? "pointer" : "default", transition: "opacity 180ms ease" }}
            >
              <title>{band.label}</title>
            </path>
          );
        })}
      </svg>
      <div className="visual-ribbon-axis">
        {model.dates.map((date) => <span key={date}>{new Date(date).toLocaleDateString("en-IN", { month: "short", year: "2-digit" })}</span>)}
      </div>
      <div className="visual-ribbon-legend">
        {model.bands.map((band, index) => (
          <button type="button" key={band.label} onMouseEnter={() => setActive(band.label)} onMouseLeave={() => setActive(null)} onClick={() => onSelect?.(band.label)}>
            <i style={{ background: VISUAL_COLORS[index % VISUAL_COLORS.length] }} aria-hidden="true" /> {band.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export type HistogramBin = { label: string; count: number; bin_start: number; bin_end: number };

/** Histogram of an observed measure distribution. */
export function HistogramChart({ bins, height = 280 }: { bins: HistogramBin[]; height?: number }) {
  const animation = useChartAnimation();
  if (!bins.length) return <ChartEmpty />;
  return (
    <div className="visual-chart" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart key={animation.isAnimationActive ? "animated" : "static"} data={bins} margin={{ top: 10, right: 10, bottom: 22, left: 0 }}>
          <CartesianGrid stroke="#edf0f5" strokeDasharray="3 4" vertical={false} />
          <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: "#8993a2", fontSize: 8 }} angle={-18} textAnchor="end" height={44} interval={0} />
          <YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fill: "#8993a2", fontSize: 9 }} />
          <Tooltip formatter={(value) => [`${formatNumber(Number(value), 0)} records`, "Count"]} />
          <Bar dataKey="count" name="Records" fill={VISUAL_COLORS[2]} radius={[3, 3, 0, 0]} isAnimationActive={animation.isAnimationActive} animationDuration={animation.animationDuration} animationEasing={animation.animationEasing} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export type BoxRow = { label: string; min: number; q1: number; median: number; q3: number; max: number; mean?: number; count: number };

/** Horizontal box-and-whisker plot built from real quartiles. */
export function BoxPlotChart({ rows }: { rows: BoxRow[] }) {
  if (!rows.length) return <ChartEmpty />;
  const min = Math.min(...rows.map((row) => row.min));
  const max = Math.max(...rows.map((row) => row.max));
  const span = max - min || 1;
  const scale = (value: number) => ((value - min) / span) * 100;

  return (
    <div className="boxplot" role="img" aria-label="Distribution of values by group">
      {rows.map((row) => (
        <div className="boxplot-row" key={row.label}>
          <span className="boxplot-label">{shortLabel(row.label, 16)}</span>
          <div className="boxplot-track">
            <span className="boxplot-whisker" style={{ left: `${scale(row.min)}%`, right: `${100 - scale(row.max)}%` }} />
            <span className="boxplot-box" style={{ left: `${scale(row.q1)}%`, width: `${Math.max(scale(row.q3) - scale(row.q1), 1)}%` }} title={`${row.label}: median ${formatCurrency(row.median)}`} />
            <span className="boxplot-median" style={{ left: `${scale(row.median)}%` }} />
          </div>
          <span className="boxplot-value">{formatCompactCurrency(row.median)}</span>
        </div>
      ))}
      <div className="boxplot-scale">
        <span>{formatCompactCurrency(min)}</span>
        <span>n = {rows.reduce((sum, row) => sum + row.count, 0).toLocaleString("en-IN")}</span>
        <span>{formatCompactCurrency(max)}</span>
      </div>
    </div>
  );
}

export type ParetoRow = { label: string; sales: number; share: number; cumulative_share: number };

/** Pareto chart: product sales bars plus cumulative contribution line. */
export function ParetoChart({ rows, height = 300, onSelect }: { rows: ParetoRow[]; height?: number; onSelect?: SelectHandler }) {
  const animation = useChartAnimation();
  if (!rows.length) return <ChartEmpty />;
  const data = rows.map((row) => ({ ...row, cumulative: row.cumulative_share * 100 }));
  return (
    <div className="visual-chart" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart key={animation.isAnimationActive ? "animated" : "static"} data={data} margin={{ top: 12, right: 8, bottom: 38, left: 0 }}>
          <CartesianGrid stroke="#edf0f5" strokeDasharray="3 4" vertical={false} />
          <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: "#8993a2", fontSize: 8 }} angle={-20} textAnchor="end" height={54} interval={0} tickFormatter={(value: string) => shortLabel(value, 12)} />
          <YAxis yAxisId="sales" tickLine={false} axisLine={false} tick={{ fill: "#8993a2", fontSize: 9 }} tickFormatter={compact} />
          <YAxis yAxisId="share" orientation="right" domain={[0, 100]} tickLine={false} axisLine={false} tick={{ fill: "#8993a2", fontSize: 9 }} tickFormatter={(value: number) => `${value}%`} />
          <Tooltip formatter={(value, name) => [name === "Cumulative" ? formatPercent(Number(value)) : formatCurrency(Number(value)), String(name)]} />
          <Legend verticalAlign="top" height={26} iconType="circle" wrapperStyle={{ fontSize: 11 }} />
          <Bar yAxisId="sales" dataKey="sales" name="Sales" fill={VISUAL_COLORS[1]} radius={[3, 3, 0, 0]} onClick={(entry: unknown) => {
            const payload = (entry as { payload?: { label?: string } })?.payload;
            if (payload?.label) onSelect?.(payload.label);
          }} isAnimationActive={animation.isAnimationActive} animationDuration={animation.animationDuration} animationEasing={animation.animationEasing} />
          <Line yAxisId="share" type="monotone" dataKey="cumulative" name="Cumulative" stroke={VISUAL_COLORS[4]} strokeWidth={2.2} dot={false} isAnimationActive={animation.isAnimationActive} animationDuration={animation.animationDuration} animationEasing={animation.animationEasing} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export type HeatmapRow = { row_label: string; col_label: string; sales: number };

/** Category × city (or similar) heatmap with server-real values. */
export function HeatmapMatrix({ rows, onSelect, valueLabel = "Sales" }: { rows: HeatmapRow[]; onSelect?: SelectHandler; valueLabel?: string }) {
  const model = useMemo(() => {
    const rowTotals = new Map<string, number>();
    const colTotals = new Map<string, number>();
    for (const row of rows) {
      rowTotals.set(row.row_label, (rowTotals.get(row.row_label) ?? 0) + row.sales);
      colTotals.set(row.col_label, (colTotals.get(row.col_label) ?? 0) + row.sales);
    }
    const rowLabels = Array.from(rowTotals.entries()).sort((a, b) => b[1] - a[1]).map(([label]) => label).slice(0, 10);
    const colLabels = Array.from(colTotals.entries()).sort((a, b) => b[1] - a[1]).map(([label]) => label).slice(0, 10);
    const max = Math.max(...rows.map((row) => row.sales), 0);
    const lookup = new Map(rows.map((row) => [`${row.row_label}||${row.col_label}`, row.sales]));
    return { rowLabels, colLabels, max, lookup };
  }, [rows]);

  if (!rows.length) return <ChartEmpty />;
  return (
    <div className="heatmap" role="table" aria-label={`${valueLabel} heatmap`}>
      <div className="heatmap-row heatmap-head" role="row">
        <span className="heatmap-label" role="columnheader">Group</span>
        {model.colLabels.map((col) => <span key={col} className="heatmap-col-label" role="columnheader" title={col}>{shortLabel(col, 8)}</span>)}
      </div>
      {model.rowLabels.map((rowLabel) => (
        <div className="heatmap-row" role="row" key={rowLabel}>
          <button type="button" className="heatmap-label heatmap-row-button" role="rowheader" onClick={() => onSelect?.(rowLabel)}>{shortLabel(rowLabel, 18)}</button>
          {model.colLabels.map((col) => {
            const value = model.lookup.get(`${rowLabel}||${col}`) ?? 0;
            const alpha = model.max ? Math.max(0.05, value / model.max) : 0;
            return (
              <span
                key={col}
                role="cell"
                className="heatmap-cell"
                style={{ background: value ? `rgba(47, 101, 167, ${alpha.toFixed(3)})` : "transparent", color: alpha > 0.62 ? "#ffffff" : "#24324a" }}
                title={`${rowLabel} · ${col}: ${formatCurrency(value)}`}
              >
                {value ? formatCompactCurrency(value) : "—"}
              </span>
            );
          })}
        </div>
      ))}
      <div className="heatmap-legend"><span>Low</span><i /><span>High {valueLabel.toLowerCase()}</span></div>
    </div>
  );
}

export type MatrixRow = { row_label: string; col_label: string; sales: number; profit: number };

/** Two-dimension matrix table with row and column totals. */
export function MatrixTable({ rows, valueKey = "sales" }: { rows: MatrixRow[]; valueKey?: "sales" | "profit" }) {
  const model = useMemo(() => {
    const rowLabels = Array.from(new Set(rows.map((row) => row.row_label))).slice(0, 12);
    const colLabels = Array.from(new Set(rows.map((row) => row.col_label))).slice(0, 12);
    const lookup = new Map(rows.map((row) => [`${row.row_label}||${row.col_label}`, row[valueKey]]));
    return { rowLabels, colLabels, lookup };
  }, [rows, valueKey]);
  if (!rows.length) return <ChartEmpty />;
  const total = rows.reduce((sum, row) => sum + row[valueKey], 0);
  return (
    <div className="table-wrap">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Group</TableHead>
            {model.colLabels.map((col) => <TableHead key={col} className="text-right">{shortLabel(col, 14)}</TableHead>)}
            <TableHead className="text-right">Total</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {model.rowLabels.map((rowLabel) => {
            const rowTotal = model.colLabels.reduce((sum, col) => sum + (model.lookup.get(`${rowLabel}||${col}`) ?? 0), 0);
            return (
              <TableRow key={rowLabel}>
                <TableCell>{rowLabel}</TableCell>
                {model.colLabels.map((col) => <TableCell key={col} className="text-right">{formatCompactCurrency(model.lookup.get(`${rowLabel}||${col}`) ?? 0)}</TableCell>)}
                <TableCell className="text-right"><strong>{formatCompactCurrency(rowTotal)}</strong></TableCell>
              </TableRow>
            );
          })}
          <TableRow>
            <TableCell><strong>Total</strong></TableCell>
            {model.colLabels.map((col) => {
              const colTotal = model.rowLabels.reduce((sum, rowLabel) => sum + (model.lookup.get(`${rowLabel}||${col}`) ?? 0), 0);
              return <TableCell key={col} className="text-right"><strong>{formatCompactCurrency(colTotal)}</strong></TableCell>;
            })}
            <TableCell className="text-right"><strong>{formatCompactCurrency(total)}</strong></TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
  );
}

export type DecompositionNode = { label: string; value: number; children?: DecompositionNode[] };

/** Category-to-product decomposition tree. */
export function DecompositionTree({ tree, onSelect }: { tree: DecompositionNode | null; onSelect?: SelectHandler }) {
  if (!tree || !tree.children?.length) return <ChartEmpty message="No category and product hierarchy is available for this dataset." />;
  const max = Math.max(...tree.children.map((child) => child.value), 1);
  return (
    <div className="decomp-tree">
      <div className="decomp-root">
        <span>{tree.label}</span>
        <strong>{formatCompactCurrency(tree.value)}</strong>
      </div>
      <div className="decomp-branches">
        {tree.children.map((category, index) => (
          <div className="decomp-branch" key={category.label}>
            <button type="button" className="decomp-category" style={{ borderColor: VISUAL_COLORS[index % VISUAL_COLORS.length] }} onClick={() => onSelect?.(category.label)}>
              <span>{category.label}</span>
              <strong>{formatCompactCurrency(category.value)}</strong>
              <i style={{ width: `${(category.value / max) * 100}%`, background: VISUAL_COLORS[index % VISUAL_COLORS.length] }} aria-hidden="true" />
            </button>
            <div className="decomp-leaves">
              {(category.children ?? []).slice(0, 5).map((product) => (
                <div className="decomp-leaf" key={product.label}>
                  <span>{shortLabel(product.label, 20)}</span>
                  <strong>{formatCompactCurrency(product.value)}</strong>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export type InfluencerRow = { label: string; sales: number; profit: number; share: number | null; margin: number | null; margin_delta: number | null };

/** Key-influencer ranking based on real sales share and margin difference. */
export function KeyInfluencers({ rows, onSelect }: { rows: InfluencerRow[]; onSelect?: SelectHandler }) {
  if (!rows.length) return <ChartEmpty />;
  const max = Math.max(...rows.map((row) => row.sales), 1);
  return (
    <ol className="influencer-list">
      {rows.map((row, index) => (
        <li key={row.label}>
          <button type="button" className="influencer-row" onClick={() => onSelect?.(row.label)}>
            <span className="influencer-rank">{String(index + 1).padStart(2, "0")}</span>
            <span className="influencer-name">{row.label}</span>
            <span className="influencer-track"><i style={{ width: `${(row.sales / max) * 100}%` }} /></span>
            <span className="influencer-value">{formatCompactCurrency(row.sales)}</span>
            <span className="influencer-share">{row.share != null ? formatPercent(row.share * 100) : "—"}</span>
            <span className={row.margin_delta != null && row.margin_delta < 0 ? "influencer-delta negative" : "influencer-delta"}>
              {row.margin_delta != null ? `${row.margin_delta >= 0 ? "+" : ""}${(row.margin_delta * 100).toFixed(1)} pts` : "—"}
            </span>
          </button>
        </li>
      ))}
    </ol>
  );
}
