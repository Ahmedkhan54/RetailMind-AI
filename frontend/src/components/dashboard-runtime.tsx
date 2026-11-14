"use client";

import { useState, useSyncExternalStore } from "react";
import useSWR from "swr";
import { AnalyticsDateFilter } from "@/components/analytics-date-filter";
import { CustomizeDashboard, DashboardModeBar, type DashboardMode } from "@/components/dashboard-customizer";
import { ExecutiveOverview, type Overview } from "@/components/executive-overview";
import { fetchJson, useDataset } from "@/components/providers";
import { DashboardPage } from "@/components/dashboard-page";
import { CircleAlert } from "lucide-react";

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
  const { data, error, isLoading } = useSWR<Overview>(endpoint, fetchJson);

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
    <ExecutiveOverview
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
