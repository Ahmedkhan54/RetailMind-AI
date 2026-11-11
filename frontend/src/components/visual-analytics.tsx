"use client";

import { useMemo, useState, type ReactNode } from "react";
import useSWR from "swr";
import Link from "next/link";
import { AnalyticsDateFilter } from "@/components/analytics-date-filter";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  BoxPlotChart,
  CategoryRibbon,
  ChartEmpty,
  ComparisonBarChart,
  ContributionTreemap,
  DecompositionTree,
  FunnelChart,
  GaugeMeter,
  HeatmapMatrix,
  HistogramChart,
  KeyInfluencers,
  MatrixTable,
  ParetoChart,
  SalesProfitScatter,
  ShareDonut,
  TrendChart,
  WaterfallChart,
} from "@/components/visual-charts";
import { useDataset } from "@/components/providers";
import { useChartAnimation } from "@/lib/animation-preference";
import { formatCompactCurrency, formatCurrency, formatNumber, formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { NavigationItem } from "@/lib/navigation";
import {
  EMPTY_FILTERS,
  downloadRowsCsv,
  fetchVisuals,
  visualEndpoint,
  type DimensionRow,
  type VisualFilters,
  type VisualPayload,
} from "@/lib/visual-types";
import { CircleAlert, Database, Download, Filter, MapPinned, Sparkles, Table2, TrendingUp } from "lucide-react";

type Tab = "compare" | "distribution" | "relationships" | "matrix";
type GroupBy = "category" | "product_name" | "city" | "region";
type Measure = "sales" | "profit";
type SortKey = "sales" | "profit" | "margin";

const TABS: { id: Tab; label: string; description: string }[] = [
  { id: "compare", label: "Compare", description: "Clustered, stacked, line, area, and combo charts" },
  { id: "distribution", label: "Distribution", description: "Pie, treemap, histogram, box plot, and Pareto" },
  { id: "relationships", label: "Relationships", description: "Scatter, bubble, waterfall, funnel, gauge, and ribbon" },
  { id: "matrix", label: "Matrix & drivers", description: "Heatmap, matrix table, decomposition tree, and influences" },
];

const GROUP_LABELS: Record<GroupBy, string> = {
  category: "Category",
  product_name: "Product",
  city: "City",
  region: "Region / state",
};

function Panel({ title, subtitle, action, children, className }: { title: string; subtitle?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <Card className={cn("panel-card", className)}>
      <CardHeader className="panel-header">
        <div>
          <CardTitle className="panel-title">{title}</CardTitle>
          {subtitle ? <p className="panel-subtitle">{subtitle}</p> : null}
        </div>
        {action}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function MetricTile({ label, value, footnote }: { label: string; value: number | null; footnote: string }) {
  return (
    <Card className="metric-card">
      <CardContent className="metric-content">
        <div className="metric-topline"><span className="metric-label">{label}</span></div>
        <div className="metric-value"><AnimatedNumber value={value} format={(current) => formatCompactCurrency(current)} /></div>
        <div className="metric-footnote">{footnote}</div>
      </CardContent>
    </Card>
  );
}

function labelValue(row: DimensionRow, key: GroupBy): string {
  const value = row[key];
  return value == null || value === "" ? "Unmapped" : String(value);
}

function categoryLabel(value: string): string {
  return value.replaceAll("_", " ");
}

export function VisualAnalyticsPage({ item }: { item: NavigationItem }) {
  const { dataset } = useDataset();
  const [filters, setFilters] = useState<VisualFilters>(EMPTY_FILTERS);
  const [tab, setTab] = useState<Tab>("compare");
  const [groupBy, setGroupBy] = useState<GroupBy>("category");
  const [measure, setMeasure] = useState<Measure>("sales");
  const [barStyle, setBarStyle] = useState<"clustered" | "stacked" | "horizontal">("clustered");
  const [trendMode, setTrendMode] = useState<"line" | "area" | "combo">("line");
  const [sortKey, setSortKey] = useState<SortKey>("sales");
  const [sortDescending, setSortDescending] = useState(true);
  const [drillLabel, setDrillLabel] = useState("");
  const [search, setSearch] = useState("");

  const endpoint = dataset ? visualEndpoint(dataset.id, filters) : null;
  const { data, error, isLoading } = useSWR<VisualPayload>(endpoint, fetchVisuals);
  const { isAnimationActive } = useChartAnimation();

  const groupRows = useMemo<DimensionRow[]>(() => {
    if (!data) return [];
    if (groupBy === "product_name") return data.products;
    if (groupBy === "city") return data.cities;
    if (groupBy === "region") return data.regions;
    return data.categories;
  }, [data, groupBy]);

  const comparisonRows = useMemo(() => groupRows.slice(0, 14), [groupRows]);

  const detailRows = useMemo(() => {
    const text = search.trim().toLowerCase();
    const rows = groupRows.filter((row) => !text || labelValue(row, groupBy).toLowerCase().includes(text));
    return [...rows].sort((left, right) => {
      const a = sortKey === "margin" ? left.margin : left[sortKey];
      const b = sortKey === "margin" ? right.margin : right[sortKey];
      const leftValue = typeof a === "number" ? a : Number.NEGATIVE_INFINITY;
      const rightValue = typeof b === "number" ? b : Number.NEGATIVE_INFINITY;
      return sortDescending ? rightValue - leftValue : leftValue - rightValue;
    });
  }, [groupRows, groupBy, search, sortKey, sortDescending]);

  const drillProducts = useMemo(() => {
    if (!data || !drillLabel) return [];
    return data.product_category.filter((row) => row.category === drillLabel).slice(0, 20);
  }, [data, drillLabel]);

  function updateFilter(key: keyof VisualFilters, value: string) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function applyCrossFilter(kind: "category" | "city" | "region", value: string) {
    setFilters((current) => ({ ...current, [kind]: current[kind] === value ? "" : value }));
  }

  function selectGroup(value: string) {
    if (groupBy === "category") applyCrossFilter("category", value);
    else if (groupBy === "city") applyCrossFilter("city", value);
    else if (groupBy === "region") applyCrossFilter("region", value);
    else setDrillLabel(value);
  }

  function clearFilters() {
    setFilters(EMPTY_FILTERS);
    setDrillLabel("");
    setSearch("");
  }

  const activeChips = (Object.keys(filters) as (keyof VisualFilters)[])
    .filter((key) => key !== "dateFrom" && key !== "dateTo" && filters[key])
    .map((key) => ({ key, value: filters[key] }));

  const kpis = data?.kpis;
  const margin = typeof kpis?.profit_margin === "number" ? kpis.profit_margin * 100 : null;
  const regionAvailable = Boolean(data?.dimensions?.region);
  const totalSales = typeof kpis?.total_sales === "number" ? kpis.total_sales : null;
  const totalProfit = typeof kpis?.total_profit === "number" ? kpis.total_profit : null;

  return (
    <div className="page-stack">
      <section className="page-heading-row">
        <div>
          <p className="eyebrow">Advanced visual analytics</p>
          <h1 className="page-title">{item.label}</h1>
          <p className="page-description">Every chart below is calculated from <strong>{dataset?.filename ?? "the active dataset"}</strong> by the Python analytics engine — no sample or fabricated values.</p>
        </div>
        <div className="page-actions">
          <Link href="/india-map" className={cn(buttonVariants({ variant: "outline", size: "lg" }), "action-button")}><MapPinned aria-hidden="true" /> India map</Link>
        </div>
      </section>

      <div className="filter-row">
        <span className="filter-note"><Database aria-hidden="true" /> {data ? `${formatNumber(data.matched_rows ?? 0, 0)} of ${formatNumber(data.row_count ?? 0, 0)} records match` : "Select a dataset to calculate visuals"}</span>
        <AnalyticsDateFilter
          dateFrom={filters.dateFrom}
          dateTo={filters.dateTo}
          disabled={!dataset}
          onDateFromChange={(value) => updateFilter("dateFrom", value)}
          onDateToChange={(value) => updateFilter("dateTo", value)}
          onClear={() => setFilters((current) => ({ ...current, dateFrom: "", dateTo: "" }))}
        />
      </div>

      {!dataset ? <div className="backend-notice" role="status"><CircleAlert aria-hidden="true" /><span>Choose or upload a dataset to use visual analytics. <Link href="/upload" className="text-action">Upload a dataset</Link></span></div> : null}
      {isLoading ? <div className="loading-panel" aria-live="polite" /> : null}
      {error ? <p className="assistant-error" role="alert">{error.message}</p> : null}
      {data && !data.available ? <div className="backend-notice" role="status"><CircleAlert aria-hidden="true" /><span>{data.notes.join(" ") || "This dataset cannot yet support the required visual fields."}</span></div> : null}

      {data?.available ? (
        <>
          <section className="filter-row visual-filter-row" aria-label="Visual filters">
            {(["category", "city", "region"] as const).map((key) => (
              <label className="compact-field" key={key}>
                <span>{key === "region" ? "Region / state" : key}</span>
                <select value={filters[key]} onChange={(event) => updateFilter(key, event.target.value)} disabled={!data.filters[key].length}>
                  <option value="">All {key === "region" ? "regions" : `${key} values`}</option>
                  {data.filters[key].map((value) => <option key={value} value={value}>{value}</option>)}
                </select>
              </label>
            ))}
            <label className="compact-field">
              <span>Group by</span>
              <select value={groupBy} onChange={(event) => setGroupBy(event.target.value as GroupBy)}>
                {Object.entries(GROUP_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
              </select>
            </label>
            <label className="compact-field">
              <span>Measure</span>
              <select value={measure} onChange={(event) => setMeasure(event.target.value as Measure)}>
                <option value="sales">Sales</option>
                <option value="profit">Profit</option>
              </select>
            </label>
            <Button type="button" variant="outline" size="sm" onClick={clearFilters} disabled={!activeChips.length && !filters.dateFrom && !filters.dateTo && !drillLabel}><Filter aria-hidden="true" /> Clear filters</Button>
            <Button type="button" variant="outline" size="sm" onClick={() => downloadRowsCsv("visual-analytics.csv", detailRows.map((row) => ({ [groupBy]: labelValue(row, groupBy), sales: row.sales, profit: row.profit, margin: row.margin ?? "" })))} disabled={!detailRows.length}><Download aria-hidden="true" /> Export view</Button>
          </section>

          {activeChips.length ? (
            <div className="visual-filter-chips" aria-label="Active filters">
              {activeChips.map((chip) => (
                <button type="button" key={chip.key} onClick={() => updateFilter(chip.key, "")}>{chip.key}: {chip.value} <span aria-hidden="true">×</span></button>
              ))}
            </div>
          ) : null}

          <section className="metric-grid" aria-label="Filtered visual analytics metrics">
            <MetricTile label="Total sales" value={totalSales} footnote={`${formatNumber(data.matched_rows ?? 0, 0)} matching records`} />
            <MetricTile label="Total profit" value={totalProfit} footnote="From the same filtered frame" />
            <Card className="metric-card"><CardContent className="metric-content"><div className="metric-topline"><span className="metric-label">Profit margin</span></div><div className="metric-value"><AnimatedNumber value={margin} format={(current) => formatPercent(current)} /></div><div className="metric-footnote">Profit ÷ sales</div></CardContent></Card>
            <MetricTile label="Average order value" value={typeof kpis?.average_order_value === "number" ? kpis.average_order_value : null} footnote="Orders aggregated first" />
            <Card className="metric-card"><CardContent className="metric-content"><div className="metric-topline"><span className="metric-label">Orders</span></div><div className="metric-value"><AnimatedNumber value={typeof kpis?.order_count === "number" ? kpis.order_count : null} format={(current) => formatNumber(current, 0)} /></div><div className="metric-footnote">Distinct order identifiers</div></CardContent></Card>
          </section>

          <div className="visual-tabs" role="tablist" aria-label="Visual analytics sections">
            {TABS.map((entry) => (
              <button key={entry.id} type="button" role="tab" aria-selected={tab === entry.id} className={cn("visual-tab", tab === entry.id && "is-active")} onClick={() => setTab(entry.id)}>
                <strong>{entry.label}</strong>
                <span>{entry.description}</span>
              </button>
            ))}
          </div>

          {tab === "compare" ? (
            <>
              <div className="visual-chart-toolbar">
                <label className="compact-field"><span>Bar style</span><select value={barStyle} onChange={(event) => setBarStyle(event.target.value as typeof barStyle)}><option value="clustered">Clustered</option><option value="stacked">Stacked</option><option value="horizontal">Horizontal</option></select></label>
                <label className="compact-field"><span>Trend style</span><select value={trendMode} onChange={(event) => setTrendMode(event.target.value as typeof trendMode)}><option value="line">Line</option><option value="area">Area</option><option value="combo">Combo</option></select></label>
                <span className="dashboard-footnote">Select a bar or legend item to cross-filter every chart on this page.</span>
              </div>
              <section className="visual-grid visual-grid-two">
                <Panel title={`${GROUP_LABELS[groupBy]} ${measure === "sales" ? "sales" : "profit"} comparison`} subtitle={`Top ${comparisonRows.length} of ${groupRows.length} groups · ${barStyle === "stacked" ? "stacked" : barStyle === "horizontal" ? "horizontal" : "clustered"} bars`} action={<Badge variant="secondary">Live data</Badge>}>
                  <ComparisonBarChart rows={comparisonRows} labelKey={groupBy} primaryKey="sales" secondaryKey="profit" stacked={barStyle === "stacked"} horizontal={barStyle === "horizontal"} onSelect={selectGroup} />
                </Panel>
                <Panel title="Monthly trend" subtitle="Sales and profit over the observed months" action={<Badge variant="outline">Time series</Badge>}>
                  <TrendChart rows={data.monthly} mode={trendMode} />
                </Panel>
              </section>
              <section className="visual-grid visual-grid-two">
                <Panel title="Category vs. profit mix" subtitle="Clustered comparison of both measures">
                  <ComparisonBarChart rows={data.categories} labelKey="category" primaryKey="sales" secondaryKey="profit" onSelect={(value) => applyCrossFilter("category", value)} />
                </Panel>
                <Panel title="Region trend" subtitle={regionAvailable ? "Monthly sales by mapped region" : "No mapped region/state column was found"}>
                  {regionAvailable ? <TrendChart rows={data.region_month.map((row) => ({ ...row }))} mode="area" primaryKey="sales" secondaryKey="profit" /> : <ChartEmpty message="Map a region, state, or province column to unlock regional trends." />}
                </Panel>
              </section>
              <Panel title={`${GROUP_LABELS[groupBy]} detail`} subtitle="Sortable table with search and real filtered values" action={<Badge variant="outline">{detailRows.length} rows</Badge>}>
                <div className="visual-table-toolbar">
                  <label className="compact-field"><span>Search {categoryLabel(groupBy)}</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Filter rows…" /></label>
                  <div className="visual-sort-buttons" role="group" aria-label="Sort detail table">
                    {(["sales", "profit", "margin"] as SortKey[]).map((key) => (
                      <Button key={key} type="button" size="sm" variant={sortKey === key ? "default" : "outline"} onClick={() => {
                        if (sortKey === key) setSortDescending((value) => !value);
                        else { setSortKey(key); setSortDescending(true); }
                      }}>{categoryLabel(key)} {sortKey === key ? (sortDescending ? "↓" : "↑") : ""}</Button>
                    ))}
                  </div>
                </div>
                <div className="table-wrap">
                  <table className="visual-table">
                    <thead><tr><th>{GROUP_LABELS[groupBy]}</th><th className="text-right">Sales</th><th className="text-right">Profit</th><th className="text-right">Margin</th><th className="text-right">Share</th></tr></thead>
                    <tbody>
                      {detailRows.slice(0, 40).map((row) => {
                        const sales = typeof row.sales === "number" ? row.sales : 0;
                        const share = totalSales ? (sales / totalSales) * 100 : 0;
                        return (
                          <tr key={labelValue(row, groupBy)}>
                            <td>{labelValue(row, groupBy)}</td>
                            <td className="text-right">{formatCurrency(row.sales)}</td>
                            <td className="text-right">{formatCurrency(row.profit)}</td>
                            <td className="text-right">{typeof row.margin === "number" ? formatPercent(row.margin * 100) : "—"}</td>
                            <td className="text-right">{formatPercent(share)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </Panel>
            </>
          ) : null}

          {tab === "distribution" ? (
            <>
              <section className="visual-grid visual-grid-two">
                <Panel title={`Sales share by ${categoryLabel(groupBy)}`} subtitle="Hover or focus a legend row to highlight its slice" action={<Badge variant="secondary">Donut</Badge>}>
                  <ShareDonut rows={groupRows.map((row) => ({ label: labelValue(row, groupBy), value: row.sales }))} centerLabel="Total sales" onSelect={selectGroup} />
                </Panel>
                <Panel title="Product contribution treemap" subtitle="Area is proportional to observed product sales" action={<Badge variant="outline">Treemap</Badge>}>
                  <ContributionTreemap rows={data.products.map((row) => ({ ...row }))} labelKey="product_name" onSelect={(value) => setDrillLabel(value)} />
                </Panel>
              </section>
              <section className="visual-grid visual-grid-two">
                <Panel title="Sales distribution" subtitle={`${data.histogram.sales.reduce((sum, bin) => sum + bin.count, 0).toLocaleString("en-IN")} records across ${data.histogram.sales.length} bins`}>
                  <HistogramChart bins={data.histogram.sales} />
                </Panel>
                <Panel title="Profit distribution" subtitle="Equal-width bins over observed row profit">
                  <HistogramChart bins={data.histogram.profit} />
                </Panel>
              </section>
              <section className="visual-grid visual-grid-two">
                <Panel title="Sales spread by category" subtitle="Whiskers show min/max, box shows quartiles" action={<Badge variant="outline">Box plot</Badge>}>
                  <BoxPlotChart rows={data.box.sales_by_category} />
                </Panel>
                <Panel title="Pareto of product sales" subtitle="Bars are sales; the line is cumulative contribution" action={<Badge variant="secondary">Pareto</Badge>}>
                  <ParetoChart rows={data.pareto} onSelect={(value) => setDrillLabel(value)} />
                </Panel>
              </section>
            </>
          ) : null}

          {tab === "relationships" ? (
            <>
              <section className="visual-grid visual-grid-two">
                <Panel title="Sales vs. profit scatter" subtitle="Bubble size follows sales; colour follows category" action={<Badge variant="secondary">Scatter</Badge>}>
                  <SalesProfitScatter rows={data.scatter.map((row) => ({ ...row }))} onSelect={(value) => setDrillLabel(value)} />
                </Panel>
                <Panel title="Margin gauge" subtitle="Profit margin after the active filters" action={<Badge variant="outline">Gauge</Badge>}>
                  <GaugeMeter value={margin} label="Profit margin" detail={`${formatCurrency(totalProfit)} profit on ${formatCurrency(totalSales)} sales`} />
                </Panel>
              </section>
              <section className="visual-grid visual-grid-two">
                <Panel title="Profit contribution waterfall" subtitle="Category profit contributions with a reconciled total" action={<Badge variant="outline">Waterfall</Badge>}>
                  <WaterfallChart rows={data.waterfall} onSelect={(value) => applyCrossFilter("category", value)} />
                </Panel>
                <Panel title="Product concentration funnel" subtitle="Share of sales held by the leading products" action={<Badge variant="outline">Funnel</Badge>}>
                  <FunnelChart stages={data.funnel} />
                </Panel>
              </section>
              <Panel title="Category share ribbon" subtitle={data.category_month.length ? "Thickness is each category's share of monthly sales" : "Monthly category history is unavailable"} action={<Badge variant="secondary">Ribbon</Badge>}>
                <CategoryRibbon rows={data.category_month} onSelect={(value) => applyCrossFilter("category", value)} />
              </Panel>
            </>
          ) : null}

          {tab === "matrix" ? (
            <>
              <section className="visual-grid visual-grid-two">
                <Panel title="Category × city heatmap" subtitle="Darker cells mean higher observed sales; click a row label to filter" action={<Badge variant="secondary">Heatmap</Badge>}>
                  <HeatmapMatrix rows={data.category_city} onSelect={(value) => applyCrossFilter("category", value)} />
                </Panel>
                <Panel title="Category × city matrix" subtitle="Values and totals reconcile to the filtered frame" action={<Badge variant="outline">Matrix</Badge>}>
                  <MatrixTable rows={data.category_city} />
                </Panel>
              </section>
              <section className="visual-grid visual-grid-two">
                <Panel title="Category → product decomposition" subtitle="Click a category to filter the page" action={<Badge variant="outline">Decomposition tree</Badge>}>
                  <DecompositionTree tree={data.decomposition} onSelect={(value) => applyCrossFilter("category", value)} />
                </Panel>
                <Panel title="Key influencers" subtitle="Sales share with margin difference from the overall margin" action={<Badge variant="secondary">Drivers</Badge>}>
                  <KeyInfluencers rows={data.influencers} onSelect={(value) => applyCrossFilter("category", value)} />
                </Panel>
              </section>
              {drillLabel ? (
                <Panel title={`Drill-down: ${drillLabel}`} subtitle="Products returned for the selected label" action={<Button type="button" variant="outline" size="sm" onClick={() => setDrillLabel("")}>Clear drill-down</Button>}>
                  {drillProducts.length ? (
                    <div className="table-wrap">
                      <table className="visual-table">
                        <thead><tr><th>Product</th><th>Category</th><th className="text-right">Sales</th><th className="text-right">Profit</th></tr></thead>
                        <tbody>{drillProducts.map((row) => <tr key={row.product_name}><td>{row.product_name}</td><td>{row.category}</td><td className="text-right">{formatCurrency(row.sales)}</td><td className="text-right">{formatCurrency(row.profit)}</td></tr>)}</tbody>
                      </table>
                    </div>
                  ) : <ChartEmpty message="No product rows were returned for this selection. Use the category filter for a server-side drill-down." />}
                </Panel>
              ) : (
                <div className="backend-notice" role="status"><Sparkles aria-hidden="true" /><span>Select a product in the treemap, Pareto, or scatter view, or choose <strong>Product</strong> as the group to open a drill-down table.</span></div>
              )}
            </>
          ) : null}

          {data.notes.length ? <p className="dashboard-footnote">{data.notes.join(" ")}</p> : null}
          <p className="dashboard-footnote">Animation follows the shared chart preference ({isAnimationActive ? "enabled" : "reduced"}). All totals are recalculated by <code>/api/visuals</code> after each filter.</p>
        </>
      ) : null}

      {!dataset ? (
        <div className="info-grid info-grid-three">
          <div className="info-card"><CardContent><span className="info-icon"><Table2 aria-hidden="true" /></span><strong>20+ chart types</strong><p>Comparison, trend, distribution, relationship, matrix, and driver views share one data contract.</p></CardContent></div>
          <div className="info-card"><CardContent><span className="info-icon"><TrendingUp aria-hidden="true" /></span><strong>Cross-filtering</strong><p>Selecting a bar, slice, row, or node updates the server aggregates used everywhere.</p></CardContent></div>
          <div className="info-card"><CardContent><span className="info-icon"><MapPinned aria-hidden="true" /></span><strong>Geography ready</strong><p>Mapped region/state values power the India map; cities stay in real ranked tables.</p></CardContent></div>
        </div>
      ) : null}
    </div>
  );
}
