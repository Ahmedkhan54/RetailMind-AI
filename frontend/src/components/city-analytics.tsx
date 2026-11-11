"use client";

/** City-wise analytics: interactive city map with a data-backed drill-down. */

import { useMemo, useState } from "react";
import useSWR from "swr";
import { ArrowLeft, CircleAlert, Database, Download, MapPinned, Search } from "lucide-react";
import { AnalyticsDateFilter } from "@/components/analytics-date-filter";
import { CityBubbleMap } from "@/components/city-bubble-map";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useDataset } from "@/components/providers";
import { fetchVisuals, visualEndpoint, downloadRowsCsv, type VisualPayload } from "@/lib/visual-types";
import { formatCompactCurrency, formatCurrency, formatNumber, formatPercent } from "@/lib/format";
import type { NavigationItem } from "@/lib/navigation";

function Kpi({ label, value, footnote }: { label: string; value: string; footnote: string }) {
  return (
    <Card className="metric-card">
      <CardContent className="metric-content">
        <span className="metric-label">{label}</span>
        <span className="metric-value">{value}</span>
        <span className="metric-footnote">{footnote}</span>
      </CardContent>
    </Card>
  );
}

export function CityAnalyticsPage({ item }: { item: NavigationItem }) {
  const { dataset } = useDataset();
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [category, setCategory] = useState("");
  const [selectedCity, setSelectedCity] = useState("");
  const [search, setSearch] = useState("");

  const baseUrl = dataset
    ? visualEndpoint(dataset.id, { dateFrom, dateTo, category, city: "", region: "" })
    : null;
  const detailUrl = dataset
    ? visualEndpoint(dataset.id, { dateFrom, dateTo, category, city: selectedCity, region: "" })
    : null;
  const baseQuery = useSWR<VisualPayload>(baseUrl, fetchVisuals);
  const detailQuery = useSWR<VisualPayload>(detailUrl, fetchVisuals);
  const base = baseQuery.data;
  const detail = selectedCity ? detailQuery.data : base;
  const error = baseQuery.error ?? detailQuery.error;

  const cities = useMemo(() => base?.cities ?? [], [base]);
  const filteredCities = useMemo(() => {
    const query = search.trim().toLowerCase();
    return cities.filter((row) => !query || String(row.city ?? "").toLowerCase().includes(query));
  }, [cities, search]);

  const kpis = base?.kpis;
  const totalSales = typeof kpis?.total_sales === "number" ? kpis.total_sales : null;
  const totalProfit = typeof kpis?.total_profit === "number" ? kpis.total_profit : null;
  const margin = typeof kpis?.profit_margin === "number" ? kpis.profit_margin : null;
  const orders = typeof kpis?.order_count === "number" ? kpis.order_count : null;

  const detailKpis = detail?.kpis;
  const topCity = useMemo(
    () => [...cities].sort((left, right) => Number(right.sales) - Number(left.sales))[0],
    [cities],
  );

  function resetCity() {
    setSelectedCity("");
  }

  return (
    <div className="page-stack">
      <section className="page-heading-row">
        <div>
          <p className="eyebrow">Geographic analytics</p>
          <h1 className="page-title">{item.label}</h1>
          <p className="page-description">
            City-wise sales, profit and product performance from <strong>{dataset?.filename ?? "the active dataset"}</strong>.
            Bubble size is proportional to observed sales.
          </p>
        </div>
        <div className="page-actions">
          <Button type="button" variant="outline" size="lg" disabled={!selectedCity} onClick={resetCity}>
            <ArrowLeft aria-hidden="true" /> Back to India map
          </Button>
        </div>
      </section>

      <div className="filter-row">
        <span className="filter-note"><Database aria-hidden="true" /> {cities.length ? `${cities.length} cities in the current selection` : "Select a dataset with a mapped city field"}</span>
        <div className="city-analytics-filters">
          <label className="compact-field">
            <span>Category</span>
            <select value={category} onChange={(event) => { setCategory(event.target.value); resetCity(); }} disabled={!base?.filters.category.length}>
              <option value="">All categories</option>
              {base?.filters.category.map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
          <AnalyticsDateFilter
            dateFrom={dateFrom}
            dateTo={dateTo}
            disabled={!dataset}
            onDateFromChange={setDateFrom}
            onDateToChange={setDateTo}
            onClear={() => { setDateFrom(""); setDateTo(""); }}
          />
        </div>
      </div>

      {!dataset ? <div className="backend-notice" role="status"><CircleAlert aria-hidden="true" /><span>Choose or upload a dataset to use city analytics.</span></div> : null}
      {baseQuery.isLoading ? <div className="loading-panel" aria-live="polite" /> : null}
      {error ? <p className="assistant-error" role="alert">{error.message}</p> : null}
      {base && !base.available ? <div className="backend-notice" role="status"><CircleAlert aria-hidden="true" /><span>{base.notes.join(" ") || "City analytics is unavailable for the current selection."}</span></div> : null}

      {base?.available ? (
        <>
          <section className="metric-grid" aria-label="City analytics metrics">
            <Kpi label="Total sales" value={formatCompactCurrency(totalSales)} footnote="Filter-aware city total" />
            <Kpi label="Total profit" value={formatCompactCurrency(totalProfit)} footnote="Profit across selected cities" />
            <Kpi label="Profit margin" value={margin != null ? formatPercent(margin * 100) : "—"} footnote="Profit ÷ sales" />
            <Kpi label="Orders" value={orders != null ? formatNumber(orders, 0) : "—"} footnote="Distinct mapped order IDs" />
            <Kpi label="Top city" value={topCity ? String(topCity.city) : "—"} footnote={topCity ? formatCompactCurrency(Number(topCity.sales)) : "No city values"} />
          </section>

          <section className="city-analytics-layout">
            <Card className="panel-card">
              <CardHeader className="panel-header">
                <div>
                  <CardTitle className="panel-title">India city bubble map</CardTitle>
                  <p className="panel-subtitle">Click a city to open its analytics · zoom, pan and search supported</p>
                </div>
                <Badge variant="secondary">Live data</Badge>
              </CardHeader>
              <CardContent>
                <CityBubbleMap
                  cities={cities.map((row) => ({ city: String(row.city ?? "Unmapped"), sales: Number(row.sales), profit: Number(row.profit), margin: row.margin ?? null }))}
                  selectedCity={selectedCity}
                  onSelectCity={setSelectedCity}
                  height={520}
                />
              </CardContent>
            </Card>

            <Card className="panel-card">
              <CardHeader className="panel-header">
                <div><CardTitle className="panel-title">City ranking</CardTitle><p className="panel-subtitle">Ranked by observed sales</p></div>
                <Badge variant="outline">{filteredCities.length}</Badge>
              </CardHeader>
              <CardContent>
                <label className="compact-field city-ranking-search">
                  <span><Search aria-hidden="true" /> Search city</span>
                  <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Filter cities…" />
                </label>
                <div className="map-state-list">
                  {filteredCities.slice(0, 40).map((row, index) => (
                    <button
                      type="button"
                      key={String(row.city)}
                      className={`map-state-row${selectedCity === String(row.city) ? " is-active" : ""}`}
                      onClick={() => setSelectedCity(selectedCity === String(row.city) ? "" : String(row.city))}
                    >
                      <span className="rank-number">{String(index + 1).padStart(2, "0")}</span>
                      <span className="rank-name">{String(row.city ?? "Unmapped")}</span>
                      <strong>{formatCompactCurrency(Number(row.sales))}</strong>
                      <em>{typeof row.margin === "number" ? formatPercent(row.margin * 100) : "—"}</em>
                    </button>
                  ))}
                  {!filteredCities.length ? <p className="empty-copy">No city matches this search.</p> : null}
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!cities.length}
                  onClick={() => downloadRowsCsv("city-analytics.csv", cities.map((row) => ({ city: row.city, sales: row.sales, profit: row.profit, margin: row.margin ?? "" })))}
                >
                  <Download aria-hidden="true" /> Export cities
                </Button>
              </CardContent>
            </Card>
          </section>

          <Card className="panel-card city-detail-card">
            <CardHeader className="panel-header">
              <div>
                <CardTitle className="panel-title">{selectedCity ? `${selectedCity} analytics` : "City detail"}</CardTitle>
                <p className="panel-subtitle">
                  {selectedCity
                    ? "Metrics below are filtered to this city and the active date/category selection."
                    : "Select a city on the map or in the ranking to open its detail view."}
                </p>
              </div>
              {selectedCity ? <Button type="button" size="sm" variant="outline" onClick={resetCity}>Clear city filter</Button> : <Badge variant="outline">India overview</Badge>}
            </CardHeader>
            <CardContent>
              {selectedCity && detailQuery.isLoading ? <div className="loading-panel" aria-label="Loading city detail" /> : null}
              {selectedCity && detail && !detail.available ? <p className="empty-copy">No records match this city for the current filters.</p> : null}
              {selectedCity && detail?.available ? (
                <>
                  <div className="metric-grid metric-grid-three">
                    <Kpi label="Sales" value={formatCurrency(Number(detailKpis?.total_sales ?? 0), { maximumFractionDigits: 2 })} footnote={`${formatNumber(detail?.matched_rows ?? 0, 0)} matching records`} />
                    <Kpi label="Profit" value={formatCurrency(Number(detailKpis?.total_profit ?? 0), { maximumFractionDigits: 2 })} footnote="Filtered city profit" />
                    <Kpi label="Margin" value={typeof detailKpis?.profit_margin === "number" ? formatPercent(detailKpis.profit_margin * 100) : "—"} footnote="Profit ÷ sales" />
                    <Kpi label="Orders" value={typeof detailKpis?.order_count === "number" ? formatNumber(detailKpis.order_count, 0) : "—"} footnote="Distinct order identifiers" />
                    <Kpi label="Customers" value={typeof detailKpis?.total_customers === "number" ? formatNumber(detailKpis.total_customers, 0) : "—"} footnote="Distinct customers in this city" />
                  </div>
                  <div className="table-wrap">
                    <table className="visual-table">
                      <thead><tr><th>Product</th><th className="text-right">Sales</th><th className="text-right">Profit</th><th className="text-right">Margin</th></tr></thead>
                      <tbody>
                        {(detail?.products ?? []).slice(0, 10).map((row) => (
                          <tr key={String(row.product_name)}>
                            <td>{String(row.product_name ?? "Unmapped")}</td>
                            <td className="text-right">{formatCurrency(Number(row.sales))}</td>
                            <td className="text-right">{formatCurrency(Number(row.profit))}</td>
                            <td className="text-right">{typeof row.margin === "number" ? formatPercent(row.margin * 100) : "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              ) : null}
              {!selectedCity ? (
                <div className="city-detail-placeholder">
                  <MapPinned aria-hidden="true" />
                  <p>Every figure comes from the active dataset. Cities without known coordinates remain in the ranking table and are never plotted at an invented location.</p>
                </div>
              ) : null}
            </CardContent>
          </Card>

          {base.notes.length ? <p className="dashboard-footnote">{base.notes.join(" ")}</p> : null}
        </>
      ) : null}
    </div>
  );
}
