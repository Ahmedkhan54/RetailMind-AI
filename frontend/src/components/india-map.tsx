"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import { AnalyticsDateFilter } from "@/components/analytics-date-filter";
import { IndiaMapChart, unmatchedRegions, type MapMode, type RegionValue } from "@/components/india-map-chart";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useDataset } from "@/components/providers";
import { formatCompactCurrency, formatCurrency, formatNumber, formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { NavigationItem } from "@/lib/navigation";
import { EMPTY_FILTERS, downloadRowsCsv, fetchVisuals, visualEndpoint, type VisualFilters, type VisualPayload } from "@/lib/visual-types";
import { CircleAlert, Database, Download, Layers, MapPinned, Search } from "lucide-react";

type SortKey = "sales" | "profit" | "margin";

function stateRows(payload: VisualPayload | undefined): RegionValue[] {
  const derived = payload?.states ?? [];
  if (derived.length) {
    return derived
      .map((row) => ({
        name: String(row.state),
        sales: Number(row.sales) || 0,
        profit: Number(row.profit) || 0,
        margin: row.margin,
      }))
      .sort((left, right) => right.sales - left.sales);
  }
  // Backward compatibility: an older backend only returns region rows. Those
  // are shown honestly even when they are sales zones rather than states.
  return (payload?.regions ?? [])
    .map((row) => ({
      name: row.region == null || row.region === "" ? "Unmapped" : String(row.region),
      sales: row.sales,
      profit: row.profit,
      margin: row.margin,
    }))
    .sort((left, right) => right.sales - left.sales);
}

function Kpi({ label, value, format, footnote }: { label: string; value: number | null; format: (value: number) => string; footnote: string }) {
  return (
    <Card className="metric-card">
      <CardContent className="metric-content">
        <div className="metric-topline"><span className="metric-label">{label}</span></div>
        <div className="metric-value"><AnimatedNumber value={value} format={format} /></div>
        <div className="metric-footnote">{footnote}</div>
      </CardContent>
    </Card>
  );
}

export function IndiaMapPage({ item }: { item: NavigationItem }) {
  const { dataset } = useDataset();
  const [filters, setFilters] = useState<VisualFilters>(EMPTY_FILTERS);
  const [mode, setMode] = useState<MapMode>("choropleth");
  const [stateSearch, setStateSearch] = useState("");
  const [citySearch, setCitySearch] = useState("");
  const [citySort, setCitySort] = useState<SortKey>("sales");

  const mapFilters = { ...filters, city: "", region: "", state: "" };
  const mapUrl = dataset ? visualEndpoint(dataset.id, mapFilters) : null;
  const detailUrl = dataset ? visualEndpoint(dataset.id, filters) : null;
  const mapQuery = useSWR<VisualPayload>(mapUrl, fetchVisuals, { keepPreviousData: true, revalidateOnFocus: false });
  const detailQuery = useSWR<VisualPayload>(detailUrl, fetchVisuals, { keepPreviousData: true, revalidateOnFocus: false });
  const mapData = mapQuery.data;
  const detail = detailQuery.data;
  const error = mapQuery.error ?? detailQuery.error;

  const regions = useMemo(() => stateRows(mapData), [mapData]);
  const unmatched = useMemo<RegionValue[]>(
    () => (mapData?.unmatched_regions ?? []).map((row) => ({ name: row.label, sales: row.sales, profit: 0 })),
    [mapData],
  );
  const unmatchedToShow = unmatched.length ? unmatched : unmatchedRegions(regions);
  const stateSource = mapData?.state_source ?? "region";

  const filteredStates = useMemo(() => {
    const query = stateSearch.trim().toLowerCase();
    return regions.filter((region) => !query || region.name.toLowerCase().includes(query));
  }, [regions, stateSearch]);

  const cities = useMemo(() => {
    const query = citySearch.trim().toLowerCase();
    const rows = (detail?.cities ?? []).filter((row) => !query || String(row.city ?? "").toLowerCase().includes(query));
    return [...rows].sort((left, right) => {
      const a = citySort === "margin" ? left.margin : left[citySort];
      const b = citySort === "margin" ? right.margin : right[citySort];
      const leftValue = typeof a === "number" ? a : Number.NEGATIVE_INFINITY;
      const rightValue = typeof b === "number" ? b : Number.NEGATIVE_INFINITY;
      return rightValue - leftValue;
    });
  }, [detail, citySearch, citySort]);

  const kpis = detail?.kpis;
  const totalSales = typeof kpis?.total_sales === "number" ? kpis.total_sales : null;
  const totalProfit = typeof kpis?.total_profit === "number" ? kpis.total_profit : null;
  const margin = typeof kpis?.profit_margin === "number" ? kpis.profit_margin * 100 : null;
  const regionSelected = filters.region;
  const stateSelected = filters.state;
  const topState = regions[0];

  function updateFilter(key: keyof VisualFilters, value: string) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function selectRegion(name: string) {
    setFilters((current) => ({ ...current, state: current.state === name ? "" : name }));
  }

  const notes = [...(mapData?.notes ?? []), ...(detail?.notes ?? [])].filter((note, index, list) => list.indexOf(note) === index);

  return (
    <div className="page-stack">
      <section className="page-heading-row">
        <div>
          <p className="eyebrow">Geographic analytics</p>
          <h1 className="page-title">{item.label}</h1>
          <p className="page-description">State-wise sales, profit, and city performance from <strong>{dataset?.filename ?? "the active dataset"}</strong>, rendered on bundled OpenStreetMap-based India boundaries.</p>
        </div>
        <div className="page-actions">
          <Link href="/visual-analytics" className={cn(buttonVariants({ variant: "outline", size: "lg" }), "action-button")}><Layers aria-hidden="true" /> Visual analytics</Link>
        </div>
      </section>

      <div className="filter-row">
        <span className="filter-note"><Database aria-hidden="true" /> {regions.length
          ? `${regions.length} states resolved · ${stateSource === "city" || stateSource === "region+city" ? "aggregated from mapped city values" : "from the mapped region field"}`
          : "Select a dataset with a mapped city or region field"}</span>
        <AnalyticsDateFilter
          dateFrom={filters.dateFrom}
          dateTo={filters.dateTo}
          disabled={!dataset}
          onDateFromChange={(value) => updateFilter("dateFrom", value)}
          onDateToChange={(value) => updateFilter("dateTo", value)}
          onClear={() => setFilters((current) => ({ ...current, dateFrom: "", dateTo: "" }))}
        />
      </div>

      {!dataset ? <div className="backend-notice" role="status"><CircleAlert aria-hidden="true" /><span>Choose or upload a dataset to use geographic analytics. <Link href="/upload" className="text-action">Upload a dataset</Link></span></div> : null}
      {mapQuery.isLoading || detailQuery.isLoading ? <div className="loading-panel" aria-live="polite" /> : null}
      {error ? <p className="assistant-error" role="alert">{error.message}</p> : null}

      {detail && !detail.available ? <div className="backend-notice" role="status"><CircleAlert aria-hidden="true" /><span>{detail.notes.join(" ") || "No records match the selected geographic filters."}</span></div> : null}

      {mapData?.available ? (
        <>
          <section className="metric-grid" aria-label="Geographic metrics">
            <Kpi label="Total sales" value={totalSales} format={(value) => formatCompactCurrency(value)} footnote={`${formatNumber(detail?.matched_rows ?? 0, 0)} matching records`} />
            <Kpi label="Total profit" value={totalProfit} format={(value) => formatCompactCurrency(value)} footnote="Filter-aware profit" />
            <Kpi label="Profit margin" value={margin} format={(value) => formatPercent(value)} footnote="Profit ÷ sales" />
            <Kpi label="Top state" value={topState?.sales ?? null} format={(value) => `${topState?.name ?? ""} · ${formatCompactCurrency(value)}`} footnote="Highest observed regional sales" />
          </section>

          <section className="filter-row visual-filter-row" aria-label="Map filters">
            <label className="compact-field"><span>State</span><select value={filters.state} onChange={(event) => updateFilter("state", event.target.value)} disabled={!(mapData.filters.state?.length)}><option value="">All states</option>{(mapData.filters.state ?? []).map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
            <label className="compact-field"><span>Sales region</span><select value={filters.region} onChange={(event) => updateFilter("region", event.target.value)} disabled={!(mapData.filters.region.length)}><option value="">All regions</option>{mapData.filters.region.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
            <label className="compact-field"><span>City</span><select value={filters.city} onChange={(event) => updateFilter("city", event.target.value)} disabled={!(mapData.filters.city.length)}><option value="">All cities</option>{mapData.filters.city.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
            <label className="compact-field"><span>Category</span><select value={filters.category} onChange={(event) => updateFilter("category", event.target.value)} disabled={!(mapData.filters.category.length)}><option value="">All categories</option>{mapData.filters.category.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
            <label className="compact-field"><span>Search states</span><input value={stateSearch} onChange={(event) => setStateSearch(event.target.value)} placeholder="e.g. Karnataka" /></label>
            <div className="visual-sort-buttons" role="group" aria-label="Map display mode">
              <Button type="button" size="sm" variant={mode === "choropleth" ? "default" : "outline"} onClick={() => setMode("choropleth")}>Choropleth</Button>
              <Button type="button" size="sm" variant={mode === "heatmap" ? "default" : "outline"} onClick={() => setMode("heatmap")}>Heatmap</Button>
              <Button type="button" size="sm" variant={mode === "bubble" ? "default" : "outline"} onClick={() => setMode("bubble")}>Bubbles</Button>
            </div>
            <Button type="button" variant="outline" size="sm" onClick={() => { setFilters(EMPTY_FILTERS); setStateSearch(""); setCitySearch(""); }}>Clear</Button>
          </section>

          {stateSelected || regionSelected || filters.city ? (
            <div className="visual-filter-chips">
              {stateSelected ? <button type="button" onClick={() => updateFilter("state", "")}>state: {stateSelected} <span aria-hidden="true">×</span></button> : null}
              {regionSelected ? <button type="button" onClick={() => updateFilter("region", "")}>region: {regionSelected} <span aria-hidden="true">×</span></button> : null}
              {filters.city ? <button type="button" onClick={() => updateFilter("city", "")}>city: {filters.city} <span aria-hidden="true">×</span></button> : null}
            </div>
          ) : null}

          <section className="visual-grid visual-grid-map">
            <Card className="panel-card">
              <CardHeader className="panel-header">
                <div><CardTitle className="panel-title">India state map</CardTitle><p className="panel-subtitle">Sales intensity by resolved state · zoom, pan, search, and click to cross-filter</p></div>
                <Badge variant="secondary">Live data</Badge>
              </CardHeader>
              <CardContent>
                <IndiaMapChart regions={regions} mode={mode} selectedRegion={filters.state} search={stateSearch} onSelectRegion={selectRegion} height={560} />
              </CardContent>
            </Card>
            <Card className="panel-card">
              <CardHeader className="panel-header">
                <div><CardTitle className="panel-title">State ranking</CardTitle><p className="panel-subtitle">Ranked by observed sales in the current selection</p></div>
                <Badge variant="outline">{filteredStates.length} states</Badge>
              </CardHeader>
              <CardContent>
                <div className="map-state-list">
                  {filteredStates.length ? filteredStates.slice(0, 30).map((region, index) => (
                    <button type="button" key={region.name} className={cn("map-state-row", filters.state === region.name && "is-active")} onClick={() => selectRegion(region.name)}>
                      <span className="rank-number">{String(index + 1).padStart(2, "0")}</span>
                      <span className="rank-name">{region.name}</span>
                      <strong>{formatCompactCurrency(region.sales)}</strong>
                      <em>{typeof region.margin === "number" ? formatPercent(region.margin * 100) : "—"}</em>
                    </button>
                  )) : <p className="empty-copy">No state values match this search.</p>}
                </div>
                <Button type="button" variant="outline" size="sm" disabled={!filteredStates.length} onClick={() => downloadRowsCsv("state-geography.csv", filteredStates.map((region) => ({ state: region.name, sales: region.sales, profit: region.profit, margin: region.margin ?? "" })))}><Download aria-hidden="true" /> Export states</Button>
              </CardContent>
            </Card>
          </section>

          {!mapData.dimensions?.city && !mapData.dimensions?.region ? (
            <div className="backend-notice" role="status"><MapPinned aria-hidden="true" /><span>The dataset has no mapped <strong>city</strong> or <strong>region/state</strong> column, so no state-level choropleth can be built.</span></div>
          ) : null}

          {unmatchedToShow.length ? (
            <Card className="panel-card">
              <CardHeader className="panel-header"><div><CardTitle className="panel-title">Unmatched location values</CardTitle><p className="panel-subtitle">These values are not state names, so they are reported here and never painted onto a boundary.</p></div><Badge variant="outline">{unmatchedToShow.length}</Badge></CardHeader>
              <CardContent>
                <div className="unmatched-regions">
                  {unmatchedToShow.map((region) => <span key={region.name}>{region.name}<em>{formatCompactCurrency(region.sales)}</em></span>)}
                </div>
              </CardContent>
            </Card>
          ) : null}

          <Card className="panel-card">
            <CardHeader className="panel-header">
              <div><CardTitle className="panel-title">City-wise analytics</CardTitle><p className="panel-subtitle">City values filtered by the selected state and date range</p></div>
              <Badge variant="secondary">{cities.length} cities</Badge>
            </CardHeader>
            <CardContent>
              <div className="visual-table-toolbar">
                <label className="compact-field"><span><Search aria-hidden="true" /> Search city</span><input value={citySearch} onChange={(event) => setCitySearch(event.target.value)} placeholder="Filter cities…" /></label>
                <div className="visual-sort-buttons" role="group" aria-label="Sort cities">
                  {(["sales", "profit", "margin"] as SortKey[]).map((key) => <Button key={key} type="button" size="sm" variant={citySort === key ? "default" : "outline"} onClick={() => setCitySort(key)}>By {key}</Button>)}
                </div>
                <Button type="button" variant="outline" size="sm" disabled={!cities.length} onClick={() => downloadRowsCsv("city-geography.csv", cities.map((row) => ({ city: row.city, sales: row.sales, profit: row.profit, margin: row.margin ?? "" })))}><Download aria-hidden="true" /> Export cities</Button>
              </div>
              <div className="table-wrap">
                <table className="visual-table">
                  <thead><tr><th>City</th><th className="text-right">Sales</th><th className="text-right">Profit</th><th className="text-right">Margin</th><th className="text-right">Action</th></tr></thead>
                  <tbody>
                    {cities.slice(0, 60).map((row) => (
                      <tr key={String(row.city)}>
                        <td>{row.city ?? "Unmapped"}</td>
                        <td className="text-right">{formatCurrency(row.sales)}</td>
                        <td className="text-right">{formatCurrency(row.profit)}</td>
                        <td className="text-right">{typeof row.margin === "number" ? formatPercent(row.margin * 100) : "—"}</td>
                        <td className="text-right"><Button type="button" size="sm" variant="outline" onClick={() => updateFilter("city", filters.city === String(row.city) ? "" : String(row.city))}>{filters.city === String(row.city) ? "Clear" : "Filter"}</Button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="dashboard-footnote">City markers use real coordinates from the bundled gazetteer on the dedicated <Link href="/city-analytics" className="text-action">City-wise Analytics</Link> page; cities without known coordinates are listed there rather than guessed. State bubbles use centroids derived from the bundled boundaries.</p>
            </CardContent>
          </Card>

          {notes.length ? <p className="dashboard-footnote">{notes.join(" ")}</p> : null}
          <p className="dashboard-footnote">Boundaries: Highcharts map collection (based on OpenStreetMap data). {stateSource === "city" || stateSource === "region+city"
            ? "State totals are summed from real city values in this dataset using the bundled city→state gazetteer; every city without a known state is listed, never guessed."
            : "State totals come only from the mapped region field in this dataset."}</p>
        </>
      ) : null}
    </div>
  );
}
