"use client";

/**
 * Additive "Customize" dashboard mode.
 *
 * The existing automatic overview dashboard is left untouched. This module
 * stores a per-dataset widget layout in localStorage and renders every widget
 * from the real overview and /api/visuals responses. No metric is generated on
 * the client.
 */

import { useId, useMemo, useRef, useState, type DragEvent } from "react";
import useSWR from "swr";
import {
  ArrowDown,
  ArrowUp,
  Check,
  GripVertical,
  LayoutDashboard,
  Plus,
  RotateCcw,
  Save,
  Settings2,
  Trash2,
} from "lucide-react";
import { AnalyticsDateFilter } from "@/components/analytics-date-filter";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  BoxPlotChart,
  ComparisonBarChart,
  ContributionTreemap,
  DecompositionTree,
  FunnelChart,
  GaugeMeter,
  HeatmapMatrix,
  HistogramChart,
  KeyInfluencers,
  ParetoChart,
  SalesProfitScatter,
  ShareDonut,
  TrendChart,
  WaterfallChart,
} from "@/components/visual-charts";
import { formatCompactCurrency, formatCurrency, formatDate, formatNumber, formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  EMPTY_FILTERS,
  fetchVisuals,
  visualEndpoint,
  type VisualFilters,
  type VisualPayload,
} from "@/lib/visual-types";
import { CircleAlert, Database, Sparkles } from "lucide-react";

export type DashboardMode = "auto" | "custom";

type WidgetKind =
  | "kpi"
  | "trend"
  | "dimension"
  | "gauge"
  | "transactions"
  | "insights"
  | "scatter"
  | "waterfall"
  | "funnel"
  | "histogram"
  | "box"
  | "pareto"
  | "heatmap"
  | "decomposition"
  | "influencers";

type Source = "categories" | "products" | "cities" | "regions";
type Measure = "sales" | "profit" | "margin";
type Aggregation = "sum" | "average" | "max" | "min";
type ChartType = "bar" | "stacked" | "horizontal" | "pie" | "treemap" | "table" | "line" | "area" | "combo";

type Widget = {
  id: string;
  title: string;
  kind: WidgetKind;
  span: 1 | 2 | 3;
  source?: Source;
  measure?: Measure;
  aggregation?: Aggregation;
  sort?: "desc" | "asc";
  top?: number;
  chartType?: ChartType;
};

type OverviewLite = {
  available: boolean;
  kpis: Record<string, number | null> | null;
  recent_transactions: { order_id: string; order_date: string; product_name: string; city: string; sales: number; profit: number }[];
  insights: string[];
  notes?: string[];
};

const SOURCE_LABELS: Record<Source, string> = {
  categories: "Category",
  products: "Product",
  cities: "City",
  regions: "Region / state",
};

const SOURCE_KEYS: Record<Source, string> = {
  categories: "category",
  products: "product_name",
  cities: "city",
  regions: "region",
};

const AGGREGATION_LABELS: Record<Aggregation, string> = {
  sum: "Sum",
  average: "Average",
  max: "Maximum",
  min: "Minimum",
};

const CHART_LABELS: Record<ChartType, string> = {
  bar: "Clustered bar",
  stacked: "Stacked bar",
  horizontal: "Horizontal bar",
  pie: "Donut",
  treemap: "Treemap",
  table: "Table",
  line: "Line",
  area: "Area",
  combo: "Combo",
};

function defaultWidgets(): Widget[] {
  return [
    { id: "kpi-sales", title: "Total sales", kind: "kpi", span: 1, measure: "sales", aggregation: "sum" },
    { id: "kpi-profit", title: "Total profit", kind: "kpi", span: 1, measure: "profit", aggregation: "sum" },
    { id: "kpi-margin", title: "Profit margin", kind: "kpi", span: 1, measure: "margin", aggregation: "average" },
    { id: "trend", title: "Sales and profit trend", kind: "trend", span: 2, chartType: "line", measure: "sales" },
    { id: "category", title: "Category performance", kind: "dimension", span: 2, source: "categories", measure: "sales", aggregation: "sum", sort: "desc", top: 8, chartType: "bar" },
    { id: "products", title: "Top products", kind: "dimension", span: 2, source: "products", measure: "sales", aggregation: "sum", sort: "desc", top: 8, chartType: "horizontal" },
    { id: "cities", title: "City performance", kind: "dimension", span: 2, source: "cities", measure: "sales", aggregation: "sum", sort: "desc", top: 8, chartType: "bar" },
    { id: "gauge", title: "Margin health", kind: "gauge", span: 1 },
    { id: "insights", title: "Evidence-based insights", kind: "insights", span: 3 },
    { id: "recent", title: "Recent transactions", kind: "transactions", span: 3 },
  ];
}

const VALID_KINDS: WidgetKind[] = ["kpi", "trend", "dimension", "gauge", "transactions", "insights", "scatter", "waterfall", "funnel", "histogram", "box", "pareto", "heatmap", "decomposition", "influencers"];
const VALID_SOURCES: Source[] = ["categories", "products", "cities", "regions"];
const VALID_MEASURES: Measure[] = ["sales", "profit", "margin"];
const VALID_AGGREGATIONS: Aggregation[] = ["sum", "average", "max", "min"];

function sanitiseWidgets(value: unknown): Widget[] | null {  if (!Array.isArray(value)) return null;
  const widgets: Widget[] = [];
  for (const entry of value) {
    if (!entry || typeof entry !== "object") continue;
    const row = entry as Record<string, unknown>;
    const kind = row.kind as WidgetKind;
    if (!VALID_KINDS.includes(kind)) continue;
    const span = row.span === 2 || row.span === 3 ? row.span : 1;
    const source = VALID_SOURCES.includes(row.source as Source) ? row.source as Source : undefined;
    const measure = VALID_MEASURES.includes(row.measure as Measure) ? row.measure as Measure : undefined;
    const aggregation = VALID_AGGREGATIONS.includes(row.aggregation as Aggregation) ? row.aggregation as Aggregation : undefined;
    widgets.push({
      id: typeof row.id === "string" && row.id ? row.id : `${kind}-${widgets.length}`,
      title: typeof row.title === "string" && row.title ? row.title : "Dashboard widget",
      kind,
      span,
      source,
      measure,
      aggregation,
      sort: row.sort === "asc" ? "asc" : row.sort === "desc" ? "desc" : undefined,
      top: typeof row.top === "number" && row.top > 0 ? row.top : undefined,
      chartType: typeof row.chartType === "string" && row.chartType in CHART_LABELS ? row.chartType as ChartType : undefined,
    });
  }
  return widgets.length ? widgets : null;
}

function initialLayout(storageKey: string): Widget[] {
  if (typeof window === "undefined") return defaultWidgets();
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (raw) {
      const parsed = sanitiseWidgets(JSON.parse(raw));
      if (parsed) return parsed;
    }
  } catch {
    /* Fall back to the curated default layout. */
  }
  return defaultWidgets();
}

function sourceRows(visuals: VisualPayload, source: Source) {
  const rows = source === "products" ? visuals.products : source === "cities" ? visuals.cities : source === "regions" ? visuals.regions : visuals.categories;
  return rows.map((row) => ({
    label: row[SOURCE_KEYS[source]] == null || row[SOURCE_KEYS[source]] === "" ? "Unmapped" : String(row[SOURCE_KEYS[source]]),
    sales: row.sales,
    profit: row.profit,
    margin: row.margin ?? null,
  }));
}

function aggregate(values: number[], mode: Aggregation): number | null {
  const usable = values.filter((value) => Number.isFinite(value));
  if (!usable.length) return null;
  if (mode === "max") return Math.max(...usable);
  if (mode === "min") return Math.min(...usable);
  const sum = usable.reduce((total, value) => total + value, 0);
  return mode === "average" ? sum / usable.length : sum;
}

function MetricText({ measure, value }: { measure: Measure | undefined; value: number | null }) {
  return (
    <AnimatedNumber
      value={value}
      format={(current) => measure === "margin" ? formatPercent(current) : measure === "profit" ? formatCurrency(current) : formatCompactCurrency(current)}
    />
  );
}

export function DashboardModeBar({ mode, onChange }: { mode: DashboardMode; onChange: (mode: DashboardMode) => void }) {
  return (
    <div className="dashboard-mode-bar" role="group" aria-label="Dashboard mode">
      <span className="dashboard-mode-label"><LayoutDashboard aria-hidden="true" /> Dashboard mode</span>
      <div className="dashboard-mode-buttons">
        <button type="button" className={cn("dashboard-mode-button", mode === "auto" && "is-active")} onClick={() => onChange("auto")} aria-pressed={mode === "auto"}>
          <strong>Auto</strong><span>Curated overview</span>
        </button>
        <button type="button" className={cn("dashboard-mode-button", mode === "custom" && "is-active")} onClick={() => onChange("custom")} aria-pressed={mode === "custom"}>
          <strong>Customize</strong><span>Your widgets</span>
        </button>
      </div>
    </div>
  );
}

function KpiWidget({ widget, visuals }: { widget: Widget; visuals: VisualPayload }) {
  const measure = widget.measure ?? "sales";
  const kpis = visuals.kpis;
  const value = measure === "margin"
    ? (typeof kpis?.profit_margin === "number" ? kpis.profit_margin * 100 : null)
    : measure === "profit"
      ? (typeof kpis?.total_profit === "number" ? kpis.total_profit : null)
      : (typeof kpis?.total_sales === "number" ? kpis.total_sales : null);
  return (
    <div className="custom-kpi">
      <span className="metric-label">{widget.title}</span>
      <div className="metric-value"><MetricText measure={measure} value={value} /></div>
      <span className="metric-footnote">Calculated after {formatNumber(visuals.matched_rows ?? 0, 0)} matching records</span>
    </div>
  );
}

function DimensionTable({ rows, measure, source }: { rows: { label: string; sales: number; profit: number; margin: number | null }[]; measure: Measure; source: Source }) {
  return (
    <div className="table-wrap">
      <table className="visual-table">
        <thead><tr><th>{SOURCE_LABELS[source]}</th><th className="text-right">Sales</th><th className="text-right">Profit</th><th className="text-right">Margin</th></tr></thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label}>
              <td>{row.label}</td>
              <td className="text-right">{formatCurrency(row.sales)}</td>
              <td className="text-right">{formatCurrency(row.profit)}</td>
              <td className="text-right">{typeof row.margin === "number" ? formatPercent(row.margin * 100) : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="dashboard-footnote">Measure: {measure} · values come from the filtered visuals response.</p>
    </div>
  );
}

function WidgetBody({ widget, visuals, overview }: { widget: Widget; visuals: VisualPayload | undefined; overview: OverviewLite | undefined }) {
  if (widget.kind === "transactions") {
    const rows = overview?.recent_transactions ?? [];
    if (!rows.length) return <div className="feature-chart-blank">No dated transactions were returned for this period.</div>;
    return (
      <div className="table-wrap recent-transactions-wrap"><table className="visual-table recent-transactions"><colgroup><col className="txn-col-order" /><col className="txn-col-date" /><col className="txn-col-product" /><col className="txn-col-city" /><col className="txn-col-sales" /></colgroup><thead><tr><th>Order</th><th>Date</th><th>Product</th><th>City</th><th className="text-right">Sales</th></tr></thead><tbody>{rows.slice(0, 8).map((row, index) => <tr key={`${row.order_id}-${index}`}><td className="txn-order" title={row.order_id}>{row.order_id}</td><td className="txn-date">{formatDate(row.order_date)}</td><td className="txn-product" title={row.product_name}>{row.product_name}</td><td className="txn-city" title={row.city}>{row.city}</td><td className="txn-sales">{formatCurrency(row.sales)}</td></tr>)}</tbody></table></div>
    );
  }
  if (widget.kind === "insights") {
    const insights = overview?.insights ?? [];
    return insights.length ? <div className="ranked-list">{insights.map((insight) => <p className="insight-copy" key={insight}>{insight}</p>)}</div> : <div className="feature-chart-blank">The insight rules did not return a statement for this dataset.</div>;
  }
  if (!visuals?.available) return <div className="feature-chart-blank">This widget needs the dataset fields used by visual analytics.</div>;

  if (widget.kind === "kpi") return <KpiWidget widget={widget} visuals={visuals} />;
  if (widget.kind === "gauge") {
    const margin = typeof visuals.kpis?.profit_margin === "number" ? visuals.kpis.profit_margin * 100 : null;
    return <GaugeMeter value={margin} label="Profit margin" detail={`${formatCurrency(visuals.kpis?.total_profit)} profit`} />;
  }
  if (widget.kind === "scatter") return <SalesProfitScatter rows={visuals.scatter} />;
  if (widget.kind === "waterfall") return <WaterfallChart rows={visuals.waterfall} />;
  if (widget.kind === "funnel") return <FunnelChart stages={visuals.funnel} />;
  if (widget.kind === "histogram") return <HistogramChart bins={visuals.histogram.sales} />;
  if (widget.kind === "box") return <BoxPlotChart rows={visuals.box.sales_by_category} />;
  if (widget.kind === "pareto") return <ParetoChart rows={visuals.pareto} />;
  if (widget.kind === "heatmap") return <HeatmapMatrix rows={visuals.category_city} />;
  if (widget.kind === "decomposition") return <DecompositionTree tree={visuals.decomposition} />;
  if (widget.kind === "influencers") return <KeyInfluencers rows={visuals.influencers} />;

  if (widget.kind === "trend") {
    const measure = widget.measure === "profit" ? "profit" : "sales";
    const rows = visuals.monthly.map((row) => ({ label: row.date, sales: row.sales, profit: row.profit }));
    if (widget.chartType === "bar") return <ComparisonBarChart rows={rows} labelKey="label" primaryKey={measure} secondaryKey={measure === "sales" ? "profit" : "sales"} horizontal={false} />;
    return <TrendChart rows={rows} mode={widget.chartType === "area" ? "area" : widget.chartType === "combo" ? "combo" : "line"} primaryKey={measure} secondaryKey={measure === "sales" ? "profit" : "sales"} primaryName={measure === "sales" ? "Sales" : "Profit"} secondaryName={measure === "sales" ? "Profit" : "Sales"} />;
  }

  if (widget.kind === "dimension") {
    const source = widget.source ?? "categories";
    const measure = widget.measure === "profit" ? "profit" : "sales";
    const aggregation = widget.aggregation ?? "sum";
    const sort = widget.sort ?? "desc";
    const top = widget.top ?? 8;
    const rows = sourceRows(visuals, source)
      .sort((left, right) => sort === "asc" ? left[measure] - right[measure] : right[measure] - left[measure])
      .slice(0, top === 0 ? undefined : top);
    const total = aggregate(rows.map((row) => row[measure]), aggregation);
    const chartType = widget.chartType ?? "bar";
    const body = chartType === "pie"
      ? <ShareDonut rows={rows.map((row) => ({ label: row.label, value: row[measure] }))} centerLabel={SOURCE_LABELS[source]} />
      : chartType === "treemap"
        ? <ContributionTreemap rows={rows.map((row) => ({ product_name: row.label, category: row.label, sales: row.sales, profit: row.profit }))} labelKey="product_name" />
        : chartType === "table"
          ? <DimensionTable rows={rows} measure={measure} source={source} />
          : <ComparisonBarChart rows={rows} labelKey="label" primaryKey={measure} secondaryKey={measure === "sales" ? "profit" : "sales"} stacked={chartType === "stacked"} horizontal={chartType === "horizontal"} />;
    return (
      <div className="dashboard-widget-chart">
        {body}
        <p className="dashboard-widget-aggregate">{AGGREGATION_LABELS[aggregation]} across {rows.length} {rows.length === 1 ? "group" : "groups"}: <strong>{measure === "sales" || measure === "profit" ? formatCurrency(total) : formatPercent(total)}</strong></p>
      </div>
    );
  }
  return null;
}

export function CustomizeDashboard({ datasetId, datasetName, onModeChange }: { datasetId: string; datasetName: string; onModeChange: (mode: DashboardMode) => void }) {
  const storageKey = `retailmind_dashboard_layout_v1:${datasetId}`;
  const [filters, setFilters] = useState<VisualFilters>(EMPTY_FILTERS);
  const [widgets, setWidgets] = useState<Widget[]>(() => initialLayout(storageKey));
  const [openConfig, setOpenConfig] = useState<string | null>(null);
  const [showCatalog, setShowCatalog] = useState(false);
  const [dragging, setDragging] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [savedSnapshot, setSavedSnapshot] = useState(() => JSON.stringify(widgets));
  const idPrefix = useId().replace(/:/g, "");
  const counter = useRef(0);

  const dateParams = new URLSearchParams();
  if (filters.dateFrom) dateParams.set("date_from", filters.dateFrom);
  if (filters.dateTo) dateParams.set("date_to", filters.dateTo);
  const overviewQuery = dateParams.toString();
  const overviewEndpoint = `/api/retailmind/dashboard/overview/${encodeURIComponent(datasetId)}${overviewQuery ? `?${overviewQuery}` : ""}`;
  const visualsQuery = useSWR<VisualPayload>(visualEndpoint(datasetId, filters), fetchVisuals);
  const overviewQueryResult = useSWR<OverviewLite>(overviewEndpoint, async (url: string) => {
    const response = await fetch(url, { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Could not load the overview.");
    return payload as OverviewLite;
  });
  const visuals = visualsQuery.data;
  const overview = overviewQueryResult.data;

  const dirty = JSON.stringify(widgets) !== savedSnapshot;

  function updateWidget(id: string, patch: Partial<Widget>) {
    setWidgets((current) => current.map((widget) => widget.id === id ? { ...widget, ...patch } : widget));
    setStatus("");
  }

  function removeWidget(id: string) {
    setWidgets((current) => current.filter((widget) => widget.id !== id));
    setOpenConfig((current) => current === id ? null : current);
    setStatus("");
  }

  function moveWidget(id: string, direction: -1 | 1) {
    setWidgets((current) => {
      const index = current.findIndex((widget) => widget.id === id);
      if (index < 0) return current;
      const target = index + direction;
      if (target < 0 || target >= current.length) return current;
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  function handleDrop(event: DragEvent<HTMLDivElement>, targetId: string) {
    event.preventDefault();
    if (!dragging || dragging === targetId) return;
    setWidgets((current) => {
      const from = current.findIndex((widget) => widget.id === dragging);
      const to = current.findIndex((widget) => widget.id === targetId);
      if (from < 0 || to < 0) return current;
      const next = [...current];
      const [moved] = next.splice(from, 1);
      next.splice(to, 0, moved);
      return next;
    });
    setDragging(null);
    setStatus("");
  }

  function saveLayout() {
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(widgets));
      setSavedSnapshot(JSON.stringify(widgets));
      setStatus("Layout saved for this dataset.");
    } catch {
      setStatus("The browser blocked layout storage; the layout still works for this session.");
    }
  }

  function restoreDefaults() {
    const defaults = defaultWidgets();
    setWidgets(defaults);
    setSavedSnapshot(JSON.stringify(defaults));
    try {
      window.localStorage.removeItem(storageKey);
    } catch {
      /* Storage can be unavailable; the default layout still applies. */
    }
    setOpenConfig(null);
    setStatus("Default layout restored.");
  }

  function addWidget(template: Omit<Widget, "id">) {
    counter.current += 1;
    const widget = { ...template, id: `${template.kind}-${idPrefix}-${counter.current}` };
    setWidgets((current) => [...current, widget]);
    setShowCatalog(false);
    setStatus("");
  }

  const catalog = useMemo<Omit<Widget, "id">[]>(() => [
    { title: "Total sales", kind: "kpi", span: 1, measure: "sales", aggregation: "sum" },
    { title: "Total profit", kind: "kpi", span: 1, measure: "profit", aggregation: "sum" },
    { title: "Profit margin", kind: "kpi", span: 1, measure: "margin", aggregation: "average" },
    { title: "Monthly trend", kind: "trend", span: 2, chartType: "line", measure: "sales" },
    { title: "Category donut", kind: "dimension", span: 1, source: "categories", measure: "sales", aggregation: "sum", sort: "desc", top: 8, chartType: "pie" },
    { title: "Product treemap", kind: "dimension", span: 2, source: "products", measure: "sales", aggregation: "sum", sort: "desc", top: 12, chartType: "treemap" },
    { title: "City ranking", kind: "dimension", span: 2, source: "cities", measure: "sales", aggregation: "sum", sort: "desc", top: 8, chartType: "horizontal" },
    { title: "Region performance", kind: "dimension", span: 2, source: "regions", measure: "sales", aggregation: "sum", sort: "desc", top: 10, chartType: "bar" },
    { title: "Margin gauge", kind: "gauge", span: 1 },
    { title: "Sales vs. profit", kind: "scatter", span: 2 },
    { title: "Profit waterfall", kind: "waterfall", span: 2 },
    { title: "Product concentration", kind: "funnel", span: 2 },
    { title: "Sales histogram", kind: "histogram", span: 2 },
    { title: "Sales spread", kind: "box", span: 2 },
    { title: "Product Pareto", kind: "pareto", span: 2 },
    { title: "Category × city heatmap", kind: "heatmap", span: 3 },
    { title: "Decomposition tree", kind: "decomposition", span: 2 },
    { title: "Key influencers", kind: "influencers", span: 2 },
    { title: "Recent transactions", kind: "transactions", span: 3 },
    { title: "Evidence-based insights", kind: "insights", span: 3 },
  ], []);

  return (
    <div className="page-stack">
      <section className="page-heading-row">
        <div><p className="eyebrow">Your business, your layout</p><h1 className="page-title">Overview dashboard</h1><p className="page-description">Calculated from <strong>{datasetName}</strong> · custom widgets are stored in this browser for this dataset.</p></div>
        <div className="page-actions"><DashboardModeBar mode="custom" onChange={onModeChange} /></div>
      </section>

      <div className="dashboard-custom-toolbar">
        <AnalyticsDateFilter dateFrom={filters.dateFrom} dateTo={filters.dateTo} onDateFromChange={(value) => setFilters((current) => ({ ...current, dateFrom: value }))} onDateToChange={(value) => setFilters((current) => ({ ...current, dateTo: value }))} onClear={() => setFilters((current) => ({ ...current, dateFrom: "", dateTo: "" }))} />
        <div className="visual-filter-row dashboard-filter-row">
          {(["category", "city", "region"] as const).map((key) => (
            <label className="compact-field" key={key}><span>{key === "region" ? "Region / state" : key}</span><select value={filters[key]} onChange={(event) => setFilters((current) => ({ ...current, [key]: event.target.value }))} disabled={!visuals?.filters[key].length}><option value="">All</option>{(visuals?.filters[key] ?? []).map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
          ))}
          <Button type="button" variant="outline" size="sm" onClick={() => setFilters(EMPTY_FILTERS)} disabled={!Object.values(filters).some(Boolean)}>Clear filters</Button>
        </div>
      </div>

      <div className="dashboard-custom-actions">
        <div className="dashboard-custom-status" aria-live="polite">{status || (dirty ? "Unsaved layout changes." : "Layout saved.")}</div>
        <div>
          <Button type="button" variant="outline" size="sm" onClick={() => setShowCatalog((value) => !value)} aria-expanded={showCatalog}><Plus aria-hidden="true" /> Add widget</Button>
          <Button type="button" variant="outline" size="sm" onClick={restoreDefaults}><RotateCcw aria-hidden="true" /> Restore default</Button>
          <Button type="button" size="sm" onClick={saveLayout} disabled={!dirty}><Save aria-hidden="true" /> Save layout</Button>
        </div>
      </div>

      {showCatalog ? (
        <Card className="panel-card dashboard-catalog">
          <CardHeader><CardTitle className="panel-title">Widget catalog</CardTitle><p className="panel-subtitle">Every widget reuses the existing chart engine and the filtered visual aggregates.</p></CardHeader>
          <CardContent>
            <div className="dashboard-catalog-grid">
              {catalog.map((template) => (
                <button type="button" key={`${template.kind}-${template.title}`} onClick={() => addWidget(template)}>
                  <strong>{template.title}</strong>
                  <span>{template.kind === "dimension" ? `${SOURCE_LABELS[template.source ?? "categories"]} · ${CHART_LABELS[template.chartType ?? "bar"]}` : template.kind.replaceAll("_", " ")}</span>
                  <Plus aria-hidden="true" />
                </button>
              ))}
            </div>
          </CardContent>
        </Card>
      ) : null}

      {visualsQuery.error || overviewQueryResult.error ? <p className="assistant-error" role="alert">{(visualsQuery.error ?? overviewQueryResult.error)?.message}</p> : null}
      {visuals && !visuals.available ? <div className="backend-notice" role="status"><CircleAlert aria-hidden="true" /><span>{visuals.notes.join(" ") || "Custom widgets need the dataset fields used by visual analytics."}</span></div> : null}

      <section className={cn("custom-dashboard-grid", !widgets.length && "is-empty")} aria-label="Custom dashboard widgets" onDragEnd={() => setDragging(null)}>
        {widgets.map((widget, index) => (
          <div
            key={widget.id}
            className={cn("custom-widget", `custom-widget-span-${widget.span}`, dragging === widget.id && "is-dragging")}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => handleDrop(event, widget.id)}
          >
            <Card className="panel-card custom-widget-card">
              <CardHeader className="custom-widget-header">
                <div className="custom-widget-heading">
                  <button
                    type="button"
                    className="custom-widget-drag"
                    draggable
                    onDragStart={() => setDragging(widget.id)}
                    title="Drag to reorder"
                    aria-label={`Drag ${widget.title} to reorder`}
                  >
                    <GripVertical aria-hidden="true" />
                  </button>
                  <div><CardTitle className="panel-title">{widget.title}</CardTitle><p className="panel-subtitle">{widget.kind === "dimension" ? `${SOURCE_LABELS[widget.source ?? "categories"]} · ${AGGREGATION_LABELS[widget.aggregation ?? "sum"]}` : widget.kind === "kpi" ? "Filtered KPI" : widget.kind.replaceAll("_", " ")}</p></div>
                </div>
                <div className="custom-widget-actions">
                  <button type="button" onClick={() => moveWidget(widget.id, -1)} disabled={index === 0} aria-label={`Move ${widget.title} earlier`}><ArrowUp aria-hidden="true" /></button>
                  <button type="button" onClick={() => moveWidget(widget.id, 1)} disabled={index === widgets.length - 1} aria-label={`Move ${widget.title} later`}><ArrowDown aria-hidden="true" /></button>
                  <button type="button" onClick={() => setOpenConfig((current) => current === widget.id ? null : widget.id)} aria-expanded={openConfig === widget.id} aria-label={`Configure ${widget.title}`}><Settings2 aria-hidden="true" /></button>
                  <button type="button" onClick={() => removeWidget(widget.id)} aria-label={`Remove ${widget.title}`}><Trash2 aria-hidden="true" /></button>
                </div>
              </CardHeader>
              {openConfig === widget.id ? (
                <div className="custom-widget-config">
                  <label className="compact-field"><span>Span</span><select value={widget.span} onChange={(event) => updateWidget(widget.id, { span: Number(event.target.value) as 1 | 2 | 3 })}><option value={1}>Small (1/3)</option><option value={2}>Medium (2/3)</option><option value={3}>Full width</option></select></label>
                  {widget.kind === "dimension" ? (
                    <>
                      <label className="compact-field"><span>Group by</span><select value={widget.source} onChange={(event) => updateWidget(widget.id, { source: event.target.value as Source })}>{VALID_SOURCES.map((source) => <option key={source} value={source}>{SOURCE_LABELS[source]}</option>)}</select></label>
                      <label className="compact-field"><span>Chart type</span><select value={widget.chartType ?? "bar"} onChange={(event) => updateWidget(widget.id, { chartType: event.target.value as ChartType })}>{(Object.keys(CHART_LABELS) as ChartType[]).filter((type) => ["bar", "stacked", "horizontal", "pie", "treemap", "table"].includes(type)).map((type) => <option key={type} value={type}>{CHART_LABELS[type]}</option>)}</select></label>
                      <label className="compact-field"><span>Sort</span><select value={widget.sort ?? "desc"} onChange={(event) => updateWidget(widget.id, { sort: event.target.value as "desc" | "asc" })}><option value="desc">Descending</option><option value="asc">Ascending</option></select></label>
                      <label className="compact-field"><span>Top groups</span><select value={widget.top ?? 8} onChange={(event) => updateWidget(widget.id, { top: Number(event.target.value) })}><option value={5}>5</option><option value={8}>8</option><option value={12}>12</option><option value={20}>20</option><option value={0}>All</option></select></label>
                    </>
                  ) : null}
                  {widget.kind === "trend" ? <label className="compact-field"><span>Chart type</span><select value={widget.chartType ?? "line"} onChange={(event) => updateWidget(widget.id, { chartType: event.target.value as ChartType })}><option value="line">Line</option><option value="area">Area</option><option value="combo">Combo</option><option value="bar">Bar</option></select></label> : null}
                  {widget.kind === "kpi" || widget.kind === "trend" || widget.kind === "dimension" ? (
                    <>
                      <label className="compact-field"><span>Measure (axis)</span><select value={widget.measure ?? "sales"} onChange={(event) => updateWidget(widget.id, { measure: event.target.value as Measure })}>{widget.kind === "kpi" ? <option value="margin">Margin</option> : null}<option value="sales">Sales</option><option value="profit">Profit</option></select></label>
                      {widget.kind === "dimension" ? <label className="compact-field"><span>Aggregation</span><select value={widget.aggregation ?? "sum"} onChange={(event) => updateWidget(widget.id, { aggregation: event.target.value as Aggregation })}>{VALID_AGGREGATIONS.map((mode) => <option key={mode} value={mode}>{AGGREGATION_LABELS[mode]}</option>)}</select></label> : null}
                    </>
                  ) : null}
                  <label className="compact-field"><span>Title</span><input value={widget.title} onChange={(event) => updateWidget(widget.id, { title: event.target.value })} /></label>
                </div>
              ) : null}
              <CardContent className="custom-widget-body">
                {visualsQuery.isLoading || overviewQueryResult.isLoading ? <div className="loading-panel" aria-live="polite" /> : <WidgetBody widget={widget} visuals={visuals} overview={overview} />}
              </CardContent>
            </Card>
          </div>
        ))}
      </section>

      {!widgets.length ? (
        <div className="dashboard-empty-custom">
          <Sparkles aria-hidden="true" />
          <p className="empty-title">Your custom dashboard is empty</p>
          <p className="empty-copy">Add a widget from the catalog to start shaping this overview.</p>
          <Button type="button" onClick={() => setShowCatalog(true)}><Plus aria-hidden="true" /> Add your first widget</Button>
        </div>
      ) : null}

      <p className="dashboard-footnote"><Check aria-hidden="true" /> Layouts are saved per dataset in this browser. The automatic dashboard remains available from the <strong>Auto</strong> mode. <Database aria-hidden="true" /> All values are recalculated by the Python backend after filters. {dirty ? <Badge variant="outline">Unsaved changes</Badge> : <Badge variant="secondary">Saved</Badge>}</p>
    </div>
  );
}
