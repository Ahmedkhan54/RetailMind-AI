"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import {
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  Boxes,
  CalendarRange,
  CircleAlert,
  CircleDollarSign,
  Download,
  MapPin,
  PackageSearch,
  RefreshCw,
  ShoppingCart,
  Sparkles,
  TrendingUp,
  Users,
} from "lucide-react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AnalyticsDateFilter } from "@/components/analytics-date-filter";
import { KpiSparkline, ProfitGauge, RevenueDonut } from "@/components/dashboard-charts";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { useChartAnimation } from "@/lib/animation-preference";
import { formatCompactCurrency, formatCurrency, formatDate, formatNumber, formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

export type Overview = {
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

type ExecutiveOverviewProps = {
  data: Overview;
  dateFrom: string;
  dateTo: string;
  onDateFromChange: (value: string) => void;
  onDateToChange: (value: string) => void;
  onClearDates: () => void;
  modeBar?: ReactNode;
};

type IconComponent = typeof BarChart3;

function monthLabel(value: string) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString("en", { month: "short" });
}

function transactionDate(value: string) {
  const raw = String(value ?? "");
  if (!raw || raw === "0" || raw.startsWith("1970-01-01")) return "—";
  return formatDate(raw);
}

function KpiCard({
  label,
  value,
  detail,
  icon: Icon,
  format,
  progress,
}: {
  label: string;
  value: number | null;
  detail: string;
  icon: IconComponent;
  format: (value: number) => string;
  progress?: number | null;
}) {
  return (
    <article className="exec-kpi exec-reveal">
      <div className="exec-kpi-top">
        <span>{label}</span>
        <span className="exec-kpi-icon"><Icon aria-hidden="true" /></span>
      </div>
      <div className="exec-kpi-value">
        <AnimatedNumber value={value} format={format} />
      </div>
      <p>{detail}</p>
      {typeof progress === "number" && Number.isFinite(progress) ? (
        <div className="exec-kpi-track" aria-hidden="true">
          <span style={{ width: `${Math.max(2, Math.min(100, progress))}%` }} />
        </div>
      ) : null}
    </article>
  );
}

function SnapshotStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="exec-snapshot-stat">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function ExecutiveOverview({
  data,
  dateFrom,
  dateTo,
  onDateFromChange,
  onDateToChange,
  onClearDates,
  modeBar,
}: ExecutiveOverviewProps) {
  const { isAnimationActive, animationDuration, animationEasing } = useChartAnimation();
  const totalSales = data.kpis?.total_sales ?? null;
  const totalProfit = data.kpis?.total_profit ?? null;
  const margin = data.kpis?.profit_margin ?? null;
  const orders = data.kpis?.order_count ?? null;
  const customers = data.kpis?.total_customers ?? null;
  const products = data.kpis?.total_products ?? null;
  const averageOrder = totalSales !== null && orders ? totalSales / orders : null;

  const monthly = [...data.sales_by_month].sort((a, b) => a.date.localeCompare(b.date));
  const currentMonth = monthly.at(-1);
  const previousMonth = monthly.at(-2);
  const monthlyGrowth = currentMonth && previousMonth && previousMonth.sales > 0
    ? ((currentMonth.sales - previousMonth.sales) / previousMonth.sales) * 100
    : null;

  const categoryRows = [...data.category_sales].sort((a, b) => b.sales - a.sales);
  const categoryTotal = categoryRows.reduce((sum, row) => sum + (Number.isFinite(row.sales) ? row.sales : 0), 0);
  const topCategory = categoryRows[0] ?? null;
  const topCategoryShare = topCategory && categoryTotal ? (topCategory.sales / categoryTotal) * 100 : null;
  const categoryProgress = categoryRows.slice(0, 5);
  const cityRows = [...data.city_performance].sort((a, b) => b.sales - a.sales);
  const cityTotal = cityRows.reduce((sum, row) => sum + (Number.isFinite(row.sales) ? row.sales : 0), 0);
  const topCities = cityRows.slice(0, 4);
  const topProducts = [...data.top_products].sort((a, b) => b.sales - a.sales).slice(0, 5);
  const maxProductSales = topProducts[0]?.sales ?? 0;
  const periodLabel = dateFrom || dateTo
    ? `${dateFrom ? formatDate(dateFrom) : "Start"} – ${dateTo ? formatDate(dateTo) : "Now"}`
    : "Full reporting period";

  return (
    <div className="exec-page">
      <section className="exec-heading">
        <div className="exec-heading-copy">
          <p className="exec-kicker"><span className="exec-live-dot" aria-hidden="true" />Executive intelligence</p>
          <h1 className="exec-title">Business command centre</h1>
          <p className="exec-subtitle">
            Live performance from <strong>{data.dataset_name}</strong> · {formatNumber(data.row_count)} records · Powered by the Python analytics API
          </p>
        </div>
        <div className="exec-heading-actions">
          <span className="exec-period"><CalendarRange aria-hidden="true" />{periodLabel}</span>
          <Link href="/export-center" className="exec-button exec-button-light"><Download aria-hidden="true" />Export report</Link>
          <Link href="/upload" className="exec-button exec-button-dark"><RefreshCw aria-hidden="true" />Change dataset</Link>
        </div>
      </section>

      {modeBar}

      <div className="exec-filter-row">
        <AnalyticsDateFilter
          dateFrom={dateFrom}
          dateTo={dateTo}
          onDateFromChange={onDateFromChange}
          onDateToChange={onDateToChange}
          onClear={onClearDates}
        />
        <span className="exec-sync"><span aria-hidden="true" />Synced with live dataset</span>
      </div>

      {!data.available ? (
        <div className="connection-banner exec-notice" role="status">
          <CircleAlert aria-hidden="true" />
          <span className="connection-copy">
            <strong>Some retail metrics are unavailable.</strong>
            <span>Map the required fields to enable sales, profit, date and category calculations: {data.missing_fields.join(", ")}.</span>
          </span>
          <Link href="/upload" className="connection-link">Review upload <ArrowRight aria-hidden="true" /></Link>
        </div>
      ) : null}

      <section aria-label="Executive performance metrics" className="exec-kpi-grid">
        <article className="exec-hero exec-reveal">
          <div className="exec-hero-top">
            <span className="exec-hero-label">Net sales</span>
            <span className="exec-hero-icon"><BarChart3 aria-hidden="true" /></span>
          </div>
          <div className="exec-hero-value">
            <AnimatedNumber value={totalSales} format={(value) => formatCurrency(value)} />
          </div>
          <div className="exec-hero-delta">
            {monthlyGrowth !== null ? (
              <>
                <span className={cn("exec-delta", monthlyGrowth < 0 && "is-negative")}>
                  <TrendingUp aria-hidden="true" />
                  {monthlyGrowth >= 0 ? "+" : ""}{formatPercent(monthlyGrowth)}
                </span>
                <span>vs previous month</span>
              </>
            ) : (
              <span className="exec-delta"><Sparkles aria-hidden="true" />Current period</span>
            )}
          </div>
          <p className="exec-hero-copy">Revenue across {formatNumber(orders)} orders in the active reporting period.</p>
          <KpiSparkline data={monthly} dataKey="sales" variant="emphasis" />
          <div className="exec-hero-footer">
            <div><span>Orders</span><strong>{formatNumber(orders)}</strong></div>
            <div><span>Avg. order</span><strong>{formatCurrency(averageOrder)}</strong></div>
          </div>
        </article>

        <KpiCard
          label="Total profit"
          value={totalProfit}
          detail="Profit after recorded cost"
          icon={CircleDollarSign}
          format={(value) => formatCurrency(value)}
        />
        <KpiCard
          label="Profit margin"
          value={typeof margin === "number" ? margin * 100 : null}
          detail="Profit as a share of sales"
          icon={TrendingUp}
          format={(value) => formatPercent(value)}
          progress={typeof margin === "number" ? margin * 100 : null}
        />
        <KpiCard
          label="Orders"
          value={orders}
          detail="Records with a valid order ID"
          icon={ShoppingCart}
          format={(value) => formatNumber(value)}
        />
        <KpiCard
          label="Customers"
          value={customers}
          detail="Distinct buyers in the dataset"
          icon={Users}
          format={(value) => formatNumber(value)}
        />
      </section>

      <div className="exec-body">
        <div className="exec-main">
          <section className="exec-card exec-chart-card exec-reveal">
            <header className="exec-card-head">
              <div>
                <h2>Revenue performance</h2>
                <p>Monthly sales and profit from the active dataset</p>
              </div>
              <div className="exec-legend" aria-label="Chart legend">
                <span><i className="is-sales" />Sales</span>
                <span><i className="is-profit" />Profit</span>
              </div>
            </header>
            {monthly.length ? (
              <div className="exec-chart">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart key={isAnimationActive ? "animated" : "static"} data={monthly} margin={{ top: 14, right: 4, left: -18, bottom: 0 }} barGap={3}>
                    <CartesianGrid stroke="#e8eee9" strokeDasharray="3 5" vertical={false} />
                    <XAxis
                      dataKey="date"
                      tickFormatter={monthLabel}
                      tickLine={false}
                      axisLine={false}
                      tick={{ fill: "#718077", fontSize: 11 }}
                      dy={6}
                    />
                    <YAxis
                      tickLine={false}
                      axisLine={false}
                      tick={{ fill: "#718077", fontSize: 11 }}
                      tickFormatter={(value: number) => new Intl.NumberFormat("en", { notation: "compact" }).format(value)}
                    />
                    <Tooltip
                      formatter={(value) => formatCurrency(Number(value))}
                      labelFormatter={(value) => new Date(String(value)).toLocaleDateString("en", { month: "long", year: "numeric" })}
                      cursor={{ fill: "#f2f7f2" }}
                      contentStyle={{ border: "1px solid #e2ebe4", borderRadius: 10, boxShadow: "0 12px 28px rgba(19, 55, 39, .09)", fontSize: 12 }}
                    />
                    <Bar
                      dataKey="sales"
                      name="Sales"
                      fill="#15513b"
                      radius={[5, 5, 0, 0]}
                      maxBarSize={28}
                      isAnimationActive={isAnimationActive}
                      animationDuration={animationDuration}
                      animationEasing={animationEasing}
                    />
                    <Bar
                      dataKey="profit"
                      name="Profit"
                      fill="#b9e26a"
                      radius={[5, 5, 0, 0]}
                      maxBarSize={28}
                      isAnimationActive={isAnimationActive}
                      animationDuration={animationDuration}
                      animationEasing={animationEasing}
                      animationBegin={100}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="exec-empty"><BarChart3 aria-hidden="true" /><span>No dated sales were returned for this period.</span></div>
            )}
            <footer className="exec-chart-footer">
              <div>
                <span>Top category</span>
                <strong>{topCategory?.category ?? "—"}</strong>
              </div>
              <div>
                <span>Category share</span>
                <strong>{topCategoryShare !== null ? formatPercent(topCategoryShare) : "—"}</strong>
              </div>
              <div>
                <span>Reporting months</span>
                <strong>{formatNumber(monthly.length, 0)}</strong>
              </div>
            </footer>
          </section>

          <div className="exec-two-col">
            <section className="exec-card exec-mix-card exec-reveal">
              <header className="exec-card-head">
                <div>
                  <h2>Revenue composition</h2>
                  <p>Category contribution to total sales</p>
                </div>
                <Link href="/category-analytics" className="exec-inline-link">Explore <ArrowUpRight aria-hidden="true" /></Link>
              </header>
              <RevenueDonut rows={data.category_sales} />
            </section>

            <section className="exec-card exec-reveal">
              <header className="exec-card-head">
                <div>
                  <h2>Top products</h2>
                  <p>Ranked by sales in this period</p>
                </div>
                <Link href="/product-analytics" className="exec-inline-link">All products <ArrowUpRight aria-hidden="true" /></Link>
              </header>
              <div className="exec-product-list">
                {topProducts.length ? topProducts.map((product, index) => (
                  <div className="exec-product" key={product.product_name}>
                    <span className="exec-product-rank">{String(index + 1).padStart(2, "0")}</span>
                    <div className="exec-product-main">
                      <div className="exec-product-line">
                        <strong>{product.product_name}</strong>
                        <span>{formatCompactCurrency(product.sales)}</span>
                      </div>
                      <div className="exec-progress" aria-hidden="true">
                        <span style={{ width: `${maxProductSales ? Math.max(4, (product.sales / maxProductSales) * 100) : 0}%` }} />
                      </div>
                      <small>{product.margin !== null ? `${formatPercent(product.margin * 100)} margin` : "Margin unavailable"}</small>
                    </div>
                  </div>
                )) : <p className="exec-empty-copy">No product column was mapped.</p>}
              </div>
            </section>
          </div>

          <section className="exec-card exec-transactions exec-reveal">
            <header className="exec-card-head">
              <div>
                <h2>Recent transactions</h2>
                <p>Latest dated records in the active dataset</p>
              </div>
              <Link href="/sales-analytics" className="exec-inline-link">Open sales analytics <ArrowUpRight aria-hidden="true" /></Link>
            </header>
            {data.recent_transactions.length ? (
              <div className="table-wrap exec-table-wrap">
                <table className="exec-table">
                  <thead>
                    <tr><th>Order</th><th>Date</th><th>Product</th><th>City</th><th>Sales</th><th>Profit</th></tr>
                  </thead>
                  <tbody>
                    {data.recent_transactions.map((row, index) => (
                      <tr key={`${row.order_id}-${index}`}>
                        <td><span className="exec-order-id">{row.order_id}</span></td>
                        <td>{transactionDate(row.order_date)}</td>
                        <td className="exec-strong-cell">{row.product_name}</td>
                        <td>{row.city || "—"}</td>
                        <td className="exec-number">{formatCurrency(row.sales)}</td>
                        <td className="exec-number exec-profit-cell">{formatCurrency(row.profit)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p className="exec-empty-copy">No dated transactions were returned for this dataset.</p>}
          </section>

          <section className="exec-card exec-insights exec-reveal">
            <header className="exec-card-head">
              <div>
                <h2>AI business insights</h2>
                <p>Evidence-based observations from the active dataset</p>
              </div>
              <span className="exec-ai-chip"><Sparkles aria-hidden="true" />Grounded</span>
            </header>
            <div className="exec-insight-list">
              {data.insights.length ? data.insights.slice(0, 3).map((insight, index) => (
                <div className="exec-insight" key={insight}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <p>{insight}</p>
                </div>
              )) : <p className="exec-empty-copy">No insight rules matched this dataset.</p>}
            </div>
            <Link href="/business-insights" className="exec-insight-link">Explore all insights <ArrowRight aria-hidden="true" /></Link>
          </section>
        </div>

        <aside className="exec-aside" aria-label="Performance analytics panel">
          <section className="exec-card exec-snapshot exec-reveal">
            <header className="exec-card-head">
              <div>
                <h2>Performance snapshot</h2>
                <p>Profit health for this period</p>
              </div>
              <span className="exec-chip">{monthly.length === 1 ? "1 month" : monthly.length ? `${monthly.length} months` : "Current"}</span>
            </header>
            <ProfitGauge margin={margin} />
            <div className="exec-snapshot-grid">
              <SnapshotStat label="Avg. order" value={formatCurrency(averageOrder)} />
              <SnapshotStat label="Customers" value={formatNumber(customers)} />
              <SnapshotStat label="Products" value={formatNumber(products)} />
              <SnapshotStat label="Cities" value={formatNumber(cityRows.length, 0)} />
            </div>
            <div className="exec-snapshot-note">
              <span className="exec-sync-dot" aria-hidden="true" />
              Profit is calculated from the same records as sales.
            </div>
          </section>

          <section className="exec-card exec-progress-card exec-reveal">
            <header className="exec-card-head">
              <div>
                <h2>Category contribution</h2>
                <p>Share of revenue</p>
              </div>
              <BarChart3 aria-hidden="true" className="exec-head-icon" />
            </header>
            <div className="exec-progress-list">
              {categoryProgress.length ? categoryProgress.map((row, index) => {
                const share = categoryTotal ? (row.sales / categoryTotal) * 100 : 0;
                return (
                  <div className="exec-progress-row" key={row.category}>
                    <div className="exec-progress-label">
                      <span><i style={{ background: ["#15513b", "#2f7d5a", "#5aa878", "#8cc79d", "#b9dfc1"][index] }} />{row.category}</span>
                      <strong>{formatPercent(share)}</strong>
                    </div>
                    <div className="exec-progress" aria-hidden="true">
                      <span style={{ width: `${Math.max(3, share)}%`, background: ["#15513b", "#2f7d5a", "#5aa878", "#8cc79d", "#b9dfc1"][index] }} />
                    </div>
                    <small>{formatCompactCurrency(row.sales)} sales</small>
                  </div>
                );
              }) : <p className="exec-empty-copy">No category data was returned.</p>}
            </div>
          </section>

          <section className="exec-card exec-progress-card exec-reveal">
            <header className="exec-card-head">
              <div>
                <h2>Top markets</h2>
                <p>City revenue share</p>
              </div>
              <MapPin aria-hidden="true" className="exec-head-icon" />
            </header>
            <div className="exec-progress-list">
              {topCities.length ? topCities.map((row, index) => {
                const share = cityTotal ? (row.sales / cityTotal) * 100 : 0;
                return (
                  <div className="exec-progress-row" key={row.city}>
                    <div className="exec-progress-label">
                      <span><i style={{ background: ["#15513b", "#2f7d5a", "#5aa878", "#8cc79d"][index] }} />{row.city || "Unmapped"}</span>
                      <strong>{formatPercent(share)}</strong>
                    </div>
                    <div className="exec-progress" aria-hidden="true">
                      <span style={{ width: `${Math.max(3, share)}%`, background: ["#15513b", "#2f7d5a", "#5aa878", "#8cc79d"][index] }} />
                    </div>
                    <small>{formatCompactCurrency(row.sales)} sales</small>
                  </div>
                );
              }) : <p className="exec-empty-copy">No city data was returned.</p>}
            </div>
            <Link href="/city-analytics" className="exec-aside-link">View city analytics <ArrowRight aria-hidden="true" /></Link>
          </section>

          <section className="exec-card exec-aside-summary exec-reveal">
            <div className="exec-aside-summary-icon"><PackageSearch aria-hidden="true" /></div>
            <div>
              <h2>{formatNumber(products)} products</h2>
              <p>Across {formatNumber(customers)} customers and {formatNumber(cityRows.length, 0)} cities in this dataset.</p>
            </div>
            <Boxes aria-hidden="true" className="exec-aside-watermark" />
          </section>
        </aside>
      </div>

      <p className="exec-footnote">All figures and charts on this page are calculated from the uploaded dataset using the existing Python backend. No target or forecast values are inferred.</p>
    </div>
  );
}
