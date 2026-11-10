"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { AnalyticsDateFilter } from "@/components/analytics-date-filter";
import { useReducedMotion } from "@/lib/use-reduced-motion";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
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

function formatCurrency(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(value);
}

function formatNumber(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 1 }).format(value);
}

function metricValue(key: string, value: number | null | undefined) {
  if (key === "total_sales" || key === "total_profit") return formatCurrency(value);
  if (key === "profit_margin") return value == null ? "—" : `${(value * 100).toFixed(1)}%`;
  return formatNumber(value);
}

const metricCards = [
  { label: "Total sales", key: "total_sales", icon: BarChart3 },
  { label: "Total profit", key: "total_profit", icon: CircleDollarSign },
  { label: "Profit margin", key: "profit_margin", icon: BarChart3 },
  { label: "Total orders", key: "order_count", icon: ShoppingCart },
  { label: "Total customers", key: "total_customers", icon: Users },
  { label: "Total products", key: "total_products", icon: Boxes },
];

function ConnectedChart({
  title,
  data,
  kind,
}: {
  title: string;
  data: Record<string, unknown>[];
  kind: "trend" | "bar";
}) {
  const reducedMotion = useReducedMotion();
  return (
    <Card className="panel-card">
      <CardHeader className="panel-header"><div><CardTitle className="panel-title">{title}</CardTitle><p className="panel-subtitle">Calculated from the active dataset</p></div><Badge variant="outline">Live data</Badge></CardHeader>
      <CardContent>
        {data.length ? (
          <div className="connected-chart">
            <ResponsiveContainer width="100%" height="100%">
              {kind === "trend" ? (
                <AreaChart data={data} margin={{ top: 12, right: 4, left: 0, bottom: 0 }}>
                  <defs><linearGradient id="salesFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#3e75bd" stopOpacity={0.2} /><stop offset="95%" stopColor="#3e75bd" stopOpacity={0} /></linearGradient></defs>
                  <CartesianGrid stroke="#edf0f5" strokeDasharray="3 4" vertical={false} />
                  <XAxis dataKey="date" tickFormatter={(value: string) => new Date(value).toLocaleDateString("en", { month: "short" })} tickLine={false} axisLine={false} tick={{ fill: "#8993a2", fontSize: 9 }} />
                  <YAxis tickLine={false} axisLine={false} tick={{ fill: "#8993a2", fontSize: 9 }} tickFormatter={(value: number) => new Intl.NumberFormat("en", { notation: "compact" }).format(value)} />
                  <Tooltip formatter={(value) => formatCurrency(Number(value))} labelFormatter={(value) => new Date(String(value)).toLocaleDateString("en", { month: "long", year: "numeric" })} />
                  <Area type="monotone" dataKey="sales" name="Sales" stroke="#2f65a7" strokeWidth={2} fill="url(#salesFill)" isAnimationActive={!reducedMotion} />
                  <Area type="monotone" dataKey="profit" name="Profit" stroke="#89a8d3" strokeWidth={2} fill="transparent" isAnimationActive={!reducedMotion} />
                </AreaChart>
              ) : (
                <BarChart data={data} layout="vertical" margin={{ top: 5, right: 10, left: 5, bottom: 5 }}>
                  <CartesianGrid stroke="#edf0f5" strokeDasharray="3 4" horizontal={false} />
                  <XAxis type="number" tickLine={false} axisLine={false} tick={{ fill: "#8993a2", fontSize: 9 }} tickFormatter={(value: number) => new Intl.NumberFormat("en", { notation: "compact" }).format(value)} />
                  <YAxis type="category" dataKey={kind === "bar" ? "label" : "date"} width={88} tickLine={false} axisLine={false} tick={{ fill: "#8993a2", fontSize: 8 }} />
                  <Tooltip formatter={(value) => formatCurrency(Number(value))} />
                  <Bar dataKey="sales" name="Sales" fill="#3e75bd" radius={[0, 5, 5, 0]} barSize={13} isAnimationActive={!reducedMotion} />
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
}: {
  data: Overview;
  dateFrom: string;
  dateTo: string;
  onDateFromChange: (value: string) => void;
  onDateToChange: (value: string) => void;
  onClearDates: () => void;
}) {
  const categories = data.category_sales.map((row) => ({ ...row, label: row.category }));
  const topProducts = data.top_products.slice(0, 5);
  const cities = data.city_performance.slice(0, 5);

  return (
    <div className="page-stack">
      <section className="page-heading-row">
        <div><p className="eyebrow">Your business, at a glance</p><h1 className="page-title">Overview dashboard</h1><p className="page-description">Calculated from <strong>{data.dataset_name}</strong> · {formatNumber(data.row_count)} records</p></div>
        <div className="page-actions"><Link href="/upload" className={cn(buttonVariants({ variant: "outline", size: "lg" }), "action-button")}>Change dataset</Link></div>
      </section>
      <AnalyticsDateFilter
        dateFrom={dateFrom}
        dateTo={dateTo}
        onDateFromChange={onDateFromChange}
        onDateToChange={onDateToChange}
        onClear={onClearDates}
      />
      {!data.available ? <div className="connection-banner" role="status"><CircleAlert aria-hidden="true" /><span className="connection-copy"><strong>Some retail metrics are unavailable.</strong><span>Map the required fields to enable sales, profit, date, and category calculations: {data.missing_fields.join(", ")}.</span></span><Link href="/upload" className="connection-link">Review upload <ArrowRight aria-hidden="true" /></Link></div> : null}
      <section aria-label="Business performance metrics" className="metric-grid">
        {metricCards.map(({ label, key, icon: Icon }) => <Card className="metric-card" key={key}><CardContent className="metric-content"><div className="metric-topline"><span className="metric-label">{label}</span><span className="metric-icon"><Icon aria-hidden="true" /></span></div><div className="metric-value">{metricValue(key, data.kpis?.[key])}</div><div className="metric-footnote">From {data.dataset_name}</div></CardContent></Card>)}
      </section>
      <section className="dashboard-grid dashboard-grid-primary"><ConnectedChart title="Sales vs. profit trends" data={data.sales_by_month} kind="trend" /><Card className="panel-card summary-card"><CardHeader><CardTitle className="panel-title">Business performance</CardTitle><p className="panel-subtitle">A summary of the current dataset</p></CardHeader><CardContent><div className="summary-placeholder"><span className="summary-ring"><BarChart3 aria-hidden="true" /></span><p className="empty-title">{formatNumber(data.row_count)} records analyzed</p><p className="empty-copy">Metrics are calculated by the existing Python analytics functions.</p><Link href="/sales-analytics" className="text-action">Explore analytics <ArrowRight aria-hidden="true" /></Link></div></CardContent></Card></section>
      <section className="dashboard-grid dashboard-grid-secondary"><ConnectedChart title="Category-wise sales" data={categories} kind="bar" /><Card className="panel-card"><CardHeader><CardTitle className="panel-title">Top performing products</CardTitle><p className="panel-subtitle">Sorted by sales</p></CardHeader><CardContent><div className="ranked-list">{topProducts.length ? topProducts.map((row, index) => <div className="ranked-row" key={row.product_name}><span className="rank-number">{String(index + 1).padStart(2, "0")}</span><span className="rank-name">{row.product_name}</span><strong>{formatCurrency(row.sales)}</strong></div>) : <p className="empty-copy">No product column was mapped.</p>}</div></CardContent></Card><Card className="panel-card"><CardHeader><CardTitle className="panel-title">City-wise performance</CardTitle><p className="panel-subtitle">Sales by city</p></CardHeader><CardContent><div className="ranked-list">{cities.length ? cities.map((row) => <div className="ranked-row" key={row.city}><span className="rank-name">{row.city}</span><strong>{formatCurrency(row.sales)}</strong></div>) : <p className="empty-copy">No city column was mapped.</p>}</div></CardContent></Card></section>
      <section className="dashboard-grid dashboard-grid-bottom"><Card className="panel-card"><CardHeader className="panel-header"><div><CardTitle className="panel-title">Recent transactions</CardTitle><p className="panel-subtitle">Latest dated records in the dataset</p></div></CardHeader><CardContent><div className="table-wrap"><Table><TableHeader><TableRow><TableHead>Order</TableHead><TableHead>Date</TableHead><TableHead>Product</TableHead><TableHead>City</TableHead><TableHead className="text-right">Sales</TableHead></TableRow></TableHeader><TableBody>{data.recent_transactions.map((row, index) => <TableRow key={`${row.order_id}-${index}`}><TableCell>{row.order_id}</TableCell><TableCell>{new Date(row.order_date).toLocaleDateString()}</TableCell><TableCell>{row.product_name}</TableCell><TableCell>{row.city}</TableCell><TableCell className="text-right">{formatCurrency(row.sales)}</TableCell></TableRow>)}</TableBody></Table></div></CardContent></Card><Card className="insight-card"><CardHeader><CardTitle className="panel-title">AI business insights</CardTitle><p className="panel-subtitle">Evidence-based observations</p></CardHeader><CardContent><div className="ranked-list">{data.insights.length ? data.insights.map((insight) => <p className="insight-copy" key={insight}>{insight}</p>) : <p className="empty-copy">No insight rules matched this dataset.</p>}</div><Link href="/business-insights" className="insight-link">Explore insights <ArrowRight aria-hidden="true" /></Link></CardContent></Card></section>
      <p className="dashboard-footnote">All figures and charts on this page are calculated from the uploaded dataset using the existing Python backend.</p>
    </div>
  );
}

export function DashboardRuntime() {
  const { dataset } = useDataset();
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const dateParams = new URLSearchParams();
  if (dateFrom) dateParams.set("date_from", dateFrom);
  if (dateTo) dateParams.set("date_to", dateTo);
  const query = dateParams.toString();
  const endpoint = dataset
    ? `/api/retailmind/dashboard/overview/${encodeURIComponent(dataset.id)}${query ? `?${query}` : ""}`
    : null;
  const { data, error, isLoading } = useSWR<Overview>(endpoint, fetchOverview);

  if (!dataset) return <DashboardPage />;
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
    />
  );
}
