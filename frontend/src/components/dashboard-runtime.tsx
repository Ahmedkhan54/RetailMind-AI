"use client";

import { useId, useState, useSyncExternalStore, type ReactNode } from "react";
import Link from "next/link";
import useSWR from "swr";
import { AnalyticsDateFilter } from "@/components/analytics-date-filter";
import { RevenueDonut, ProfitGauge, KpiSparkline } from "@/components/dashboard-charts";
import { CustomizeDashboard, DashboardModeBar, type DashboardMode } from "@/components/dashboard-customizer";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { useChartAnimation } from "@/lib/animation-preference";
import { formatCurrency, formatDate, formatNumber, formatPercent } from "@/lib/format";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ArrowRight, BarChart3, Boxes, CircleAlert, CircleDollarSign, ShoppingCart, Users } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { useDataset } from "@/components/providers";
import { DashboardPage } from "@/components/dashboard-page";

type Overview = {
  dataset_id: string;
  dataset_name: string;
  available: boolean;
  row_count: number;
  kpis: Record<string, number | null> | null;
  missing_fields: string[];
  sales_by_month: { date: string; sales: number; profit: number }[];
  category_sales: { category: string; sales: number; profit: number; margin: number | null }[];
  top_products: { product_name: string; sales: number; profit: number; margin: number | null }[];
  city_performance: { city: string; sales: number; profit: number; margin: number | null }[];
  recent_transactions: { order_id: string; order_date: string; product_name: string; city: string; sales: number; profit: number }[];
  insights: string[];
};

async function fetchOverview(url: string): Promise<Overview> {
  const response = await fetch(url, { cache: "no-store" });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "Could not load this dataset.");
  return payload as Overview;
}

const metricCards = [
  { label: "Total sales", key: "total_sales", icon: BarChart3 },
  { label: "Total profit", key: "total_profit", icon: CircleDollarSign },
  { label: "Profit margin", key: "profit_margin", icon: BarChart3 },
  { label: "Total orders", key: "order_count", icon: ShoppingCart },
  { label: "Total customers", key: "total_customers", icon: Users },
  { label: "Total products", key: "total_products", icon: Boxes },
];

function MetricValue({ metricKey, value }: { metricKey: string; value: number | null | undefined }) {
  if (metricKey === "total_sales" || metricKey === "total_profit") {
    return <AnimatedNumber value={value ?? null} format={(current) => formatCurrency(current)} />;
  }
  if (metricKey === "profit_margin") {
    return <AnimatedNumber value={typeof value === "number" ? value * 100 : null} format={(current) => formatPercent(current)} />;
  }
  return <AnimatedNumber value={value ?? null} format={(current) => formatNumber(current)} />;
}

function ConnectedChart({
  title,
  data,
  kind,
}: {
  title: string;
  data: Record<string, unknown>[];
  kind: "trend" | "bar";
}) {
  const { isAnimationActive, animationDuration, animationEasing } = useChartAnimation();
  const stripeId = `bar-stripe-${useId().replace(/:/g, "")}`;
  return (
    <Card className="panel-card">
      <CardHeader className="panel-header"><div><CardTitle className="panel-title">{title}</CardTitle><p className="panel-subtitle">Calculated from the active dataset</p></div><Badge variant="outline">Live data</Badge></CardHeader>
      <CardContent>
        {data.length ? (
          <div className="connected-chart">
            <ResponsiveContainer width="100%" height="100%">
              {kind === "trend" ? (
                <AreaChart key={isAnimationActive ? "animated" : "static"} data={data} margin={{ top: 12, right: 4, left: 0, bottom: 0 }}>
                  <defs><linearGradient id="salesFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#3e75bd" stopOpacity={0.24} /><stop offset="95%" stopColor="#3e75bd" stopOpacity={0} /></linearGradient></defs>
                  <CartesianGrid stroke="#edf0f5" strokeDasharray="3 4" vertical={false} />
                  <XAxis dataKey="date" tickFormatter={(value: string) => new Date(value).toLocaleDateString("en", { month: "short" })} tickLine={false} axisLine={false} tick={{ fill: "#8993a2", fontSize: 9 }} />
                  <YAxis tickLine={false} axisLine={false} tick={{ fill: "#8993a2", fontSize: 9 }} tickFormatter={(value: number) => new Intl.NumberFormat("en", { notation: "compact" }).format(value)} />
                  <Tooltip formatter={(value) => formatCurrency(Number(value))} labelFormatter={(value) => new Date(String(value)).toLocaleDateString("en", { month: "long", year: "numeric" })} />
                  <Area type="monotone" dataKey="sales" name="Sales" stroke="#2f65a7" strokeWidth={2.2} fill="url(#salesFill)" isAnimationActive={isAnimationActive} animationDuration={animationDuration} animationEasing={animationEasing} />
                  <Area type="monotone" dataKey="profit" name="Profit" stroke="#89a8d3" strokeWidth={1.8} strokeDasharray="5 4" fill="transparent" isAnimationActive={isAnimationActive} animationDuration={animationDuration} animationEasing={animationEasing} animationBegin={120} />
                </AreaChart>
              ) : (
                <BarChart key={isAnimationActive ? "animated" : "static"} data={data} layout="vertical" margin={{ top: 5, right: 10, left: 5, bottom: 5 }}>
                  <defs>
                    <pattern id={stripeId} width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                      <rect width="7" height="7" fill="#eaf0f8" />
                      <line x1="0" y1="0" x2="0" y2="7" stroke="#9db7da" strokeWidth="2" />
                    </pattern>
                  </defs>
                  <CartesianGrid stroke="#edf0f5" strokeDasharray="3 4" horizontal={false} />
                  <XAxis type="number" tickLine={false} axisLine={false} tick={{ fill: "#8993a2", fontSize: 9 }} tickFormatter={(value: number) => new Intl.NumberFormat("en", { notation: "compact" }).format(value)} />
                  <YAxis type="category" dataKey={kind === "bar" ? "label" : "date"} width={88} tickLine={false} axisLine={false} tick={{ fill: "#8993a2", fontSize: 8 }} />
                  <Tooltip formatter={(value) => formatCurrency(Number(value))} />
                  <Bar dataKey="sales" name="Sales" radius={[0, 5, 5, 0]} barSize={13} isAnimationActive={isAnimationActive} animationDuration={animationDuration} animationEasing={animationEasing} animationBegin={80}>
                    {data.map((entry, index) => (
                      <Cell key={String(entry.label ?? entry.category ?? index)} fill={index % 2 === 0 ? "#3e75bd" : `url(#${stripeId})`} />
                    ))}
                  </Bar>
                </BarChart>
              )}
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="feature-chart-blank"><BarChart3 aria-hidden="true" /><span>No matching records for this chart.</span></div>
        )}
      </CardContent>
    </Card>
  );
}

function ConnectedDashboard({
  data,
  dateFrom,
  dateTo,
  onDateFromChange,
  onDateToChange,
  onClearDates,
  modeBar,
}: {
  data: Overview;
  dateFrom: string;
  dateTo: string;
  onDateFromChange: (value: string) => void;
  onDateToChange: (value: string) => void;
  onClearDates: () => void;
  modeBar?: ReactNode;
}) {
  const categories = data.category_sales.map((row) => ({ ...row, label: row.category }));
  const topProducts = data.top_products.slice(0, 5);
  const cities = data.city_performance.slice(0, 5);
  const margin = data.kpis?.profit_margin;

  return (
    <div className="page-stack">
      <section className="page-heading-row">
        <div><p className="eyebrow">Your business, at a glance</p><h1 className="page-title">Overview dashboard</h1><p className="page-description">Calculated from <strong>{data.dataset_name}</strong> · {formatNumber(data.row_count)} records</p></div>
        <div className="page-actions"><Link href="/upload" className={cn(buttonVariants({ variant: "outline", size: "lg" }), "action-button")}>Change dataset</Link></div>
      </section>
      {modeBar}
      <AnalyticsDateFilter
        dateFrom={dateFrom}
        dateTo={dateTo}
        onDateFromChange={onDateFromChange}
        onDateToChange={onDateToChange}
        onClear={onClearDates}
      />
      {!data.available ? <div className="connection-banner" role="status"><CircleAlert aria-hidden="true" /><span className="connection-copy"><strong>Some retail metrics are unavailable.</strong><span>Map the required fields to enable sales, profit, date, and category calculations: {data.missing_fields.join(", ")}.</span></span><Link href="/upload" className="connection-link">Review upload <ArrowRight aria-hidden="true" /></Link></div> : null}
      <section aria-label="Business performance metrics" className="metric-grid">
        {metricCards.map(({ label, key, icon: Icon }, index) => {
          const emphasis = index === 0;
          return (
            <Card className={cn("metric-card", emphasis && "metric-card-emphasis")} key={key}>
              <CardContent className="metric-content">
                <div className="metric-topline"><span className="metric-label">{label}</span><span className="metric-icon"><Icon aria-hidden="true" /></span></div>
                <div className="metric-value"><MetricValue metricKey={key} value={data.kpis?.[key]} /></div>
                {(key === "total_sales" || key === "total_profit") ? <KpiSparkline data={data.sales_by_month} dataKey={key === "total_sales" ? "sales" : "profit"} variant={emphasis ? "emphasis" : "default"} /> : null}
                <div className="metric-footnote" title={data.dataset_name}>From active dataset</div>
              </CardContent>
            </Card>
          );
        })}
      </section>
      <section className="dashboard-grid dashboard-grid-primary"><ConnectedChart title="Sales vs. profit trends" data={data.sales_by_month} kind="trend" /><Card className="panel-card summary-card"><CardHeader><CardTitle className="panel-title">Business performance</CardTitle><p className="panel-subtitle">A summary of the current dataset</p></CardHeader><CardContent><div className="summary-placeholder"><span className="summary-ring"><BarChart3 aria-hidden="true" /></span><p className="empty-title">{formatNumber(data.row_count)} records analyzed</p><p className="empty-copy">Metrics are calculated by the existing Python analytics functions.</p><Link href="/sales-analytics" className="text-action">Explore analytics <ArrowRight aria-hidden="true" /></Link></div></CardContent></Card></section>
      <section className="dashboard-grid dashboard-grid-split" aria-label="Revenue mix and margin health">
        <Card className="panel-card">
          <CardHeader className="panel-header"><div><CardTitle className="panel-title">Revenue by category</CardTitle><p className="panel-subtitle">Share of sales in this reporting period</p></div><Badge variant="secondary">Live data</Badge></CardHeader>
          <CardContent><RevenueDonut rows={data.category_sales} /></CardContent>
        </Card>
        <Card className="panel-card">
          <CardHeader className="panel-header"><div><CardTitle className="panel-title">Margin health</CardTitle><p className="panel-subtitle">Profit as a share of sales</p></div><Badge variant="outline">Calculated</Badge></CardHeader>
          <CardContent><ProfitGauge margin={margin} /><p className="dashboard-footnote">Derived from total profit and total sales in the active dataset.</p></CardContent>
        </Card>
      </section>
      <section className="dashboard-grid dashboard-grid-secondary"><ConnectedChart title="Category-wise sales" data={categories} kind="bar" /><Card className="panel-card"><CardHeader><CardTitle className="panel-title">Top performing products</CardTitle><p className="panel-subtitle">Sorted by sales</p></CardHeader><CardContent><div className="ranked-list">{topProducts.length ? topProducts.map((row, index) => <div className="ranked-row" key={row.product_name}><span className="rank-number">{String(index + 1).padStart(2, "0")}</span><span className="rank-name">{row.product_name}</span><strong>{formatCurrency(row.sales)}</strong></div>) : <p className="empty-copy">No product column was mapped.</p>}</div></CardContent></Card><Card className="panel-card"><CardHeader><CardTitle className="panel-title">City-wise performance</CardTitle><p className="panel-subtitle">Sales by city</p></CardHeader><CardContent><div className="ranked-list">{cities.length ? cities.map((row) => <div className="ranked-row" key={row.city}><span className="rank-name">{row.city}</span><strong>{formatCurrency(row.sales)}</strong></div>) : <p className="empty-copy">No city column was mapped.</p>}</div></CardContent></Card></section>
      <section className="dashboard-grid dashboard-grid-bottom"><Card className="panel-card"><CardHeader className="panel-header"><div><CardTitle className="panel-title">Recent transactions</CardTitle><p className="panel-subtitle">Latest dated records in the dataset</p></div></CardHeader><CardContent>{data.recent_transactions.length ? <div className="table-wrap recent-transactions-wrap"><Table className="recent-transactions"><colgroup><col className="txn-col-order" /><col className="txn-col-date" /><col className="txn-col-product" /><col className="txn-col-city" /><col className="txn-col-sales" /></colgroup><TableHeader><TableRow><TableHead>Order</TableHead><TableHead>Date</TableHead><TableHead>Product</TableHead><TableHead>City</TableHead><TableHead className="text-right">Sales</TableHead></TableRow></TableHeader><TableBody>{data.recent_transactions.map((row, index) => <TableRow key={`${row.order_id}-${index}`}><TableCell className="txn-order" title={row.order_id}>{row.order_id}</TableCell><TableCell className="txn-date">{formatDate(row.order_date)}</TableCell><TableCell className="txn-product" title={row.product_name}>{row.product_name}</TableCell><TableCell className="txn-city" title={row.city}>{row.city}</TableCell><TableCell className="txn-sales">{formatCurrency(row.sales)}</TableCell></TableRow>)}</TableBody></Table></div> : <p className="empty-copy">No dated transactions were returned for this dataset.</p>}</CardContent></Card><Card className="insight-card"><CardHeader><CardTitle className="panel-title">AI business insights</CardTitle><p className="panel-subtitle">Evidence-based observations</p></CardHeader><CardContent><div className="ranked-list">{data.insights.length ? data.insights.map((insight) => <p className="insight-copy" key={insight}>{insight}</p>) : <p className="empty-copy">No insight rules matched this dataset.</p>}</div><Link href="/business-insights" className="insight-link">Explore insights <ArrowRight aria-hidden="true" /></Link></CardContent></Card></section>
      <p className="dashboard-footnote">All figures and charts on this page are calculated from the uploaded dataset using the existing Python backend.</p>
    </div>
  );
}

const DASHBOARD_MODE_KEY = "retailmind_dashboard_mode";
const dashboardModeListeners = new Set<() => void>();

function subscribeDashboardMode(listener: () => void) {
  dashboardModeListeners.add(listener);
  const onStorage = (event: StorageEvent) => {
    if (event.key === DASHBOARD_MODE_KEY) listener();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    dashboardModeListeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

function readDashboardMode(): DashboardMode {
  try {
    return window.localStorage.getItem(DASHBOARD_MODE_KEY) === "custom" ? "custom" : "auto";
  } catch {
    return "auto";
  }
}

function serverDashboardMode(): DashboardMode {
  return "auto";
}

export function DashboardRuntime() {
  const { dataset } = useDataset();
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const mode = useSyncExternalStore(subscribeDashboardMode, readDashboardMode, serverDashboardMode);

  function changeMode(next: DashboardMode) {
    try {
      window.localStorage.setItem(DASHBOARD_MODE_KEY, next);
    } catch {
      /* The current mode still applies for this session. */
    }
    dashboardModeListeners.forEach((listener) => listener());
  }

  const dateParams = new URLSearchParams();
  if (dateFrom) dateParams.set("date_from", dateFrom);
  if (dateTo) dateParams.set("date_to", dateTo);
  const query = dateParams.toString();
  const endpoint = dataset
    ? `/api/retailmind/dashboard/overview/${encodeURIComponent(dataset.id)}${query ? `?${query}` : ""}`
    : null;
  const { data, error, isLoading } = useSWR<Overview>(endpoint, fetchOverview);

  if (!dataset) return <DashboardPage />;
  if (mode === "custom") return <CustomizeDashboard key={dataset.id} datasetId={dataset.id} datasetName={dataset.filename} onModeChange={changeMode} />;
  if (error) return (
    <div className="page-stack">
      <AnalyticsDateFilter
        dateFrom={dateFrom}
        dateTo={dateTo}
        onDateFromChange={setDateFrom}
        onDateToChange={setDateTo}
        onClear={() => { setDateFrom(""); setDateTo(""); }}
      />
      <div className="backend-notice" role="alert"><CircleAlert aria-hidden="true" /><span>{error.message} Your dataset selection is available only while the Python API process is running.</span></div>
    </div>
  );
  if (isLoading || !data) return <div className="page-stack" aria-live="polite"><h1 className="page-title">Loading dataset overview</h1><div className="loading-panel" /></div>;
  return (
    <ConnectedDashboard
      data={data}
      dateFrom={dateFrom}
      dateTo={dateTo}
      onDateFromChange={setDateFrom}
      onDateToChange={setDateTo}
      onClearDates={() => { setDateFrom(""); setDateTo(""); }}
      modeBar={<DashboardModeBar mode={mode} onChange={changeMode} />}
    />
  );
}
