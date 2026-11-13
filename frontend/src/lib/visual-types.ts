/** Shared response types for the additive /api/visuals endpoint. */

export type DimensionRow = {
  [key: string]: unknown;
  category?: string | null;
  product_name?: string | null;
  city?: string | null;
  region?: string | null;
  sales: number;
  profit: number;
  margin?: number | null;
  quantity?: number | null;
};

export type HeatmapRow = { row_label: string; col_label: string; sales: number; profit: number };
export type HistogramBin = { label: string; count: number; bin_start: number; bin_end: number };
export type BoxSummary = { label: string; min: number; q1: number; median: number; q3: number; max: number; mean: number; count: number };
export type ParetoRow = { label: string; sales: number; share: number; cumulative_share: number };
export type WaterfallRow = { label: string; value: number; start: number; end: number; type: "increase" | "decrease" | "total" };
export type FunnelStage = { stage: string; value: number; share: number; products: number };
export type DecompositionNode = { label: string; value: number; children?: DecompositionNode[] };
export type InfluencerRow = { label: string; sales: number; profit: number; share: number | null; margin: number | null; margin_delta: number | null };

export type VisualPayload = {
  available: boolean;
  dataset_id: string;
  dataset_name: string;
  row_count?: number;
  matched_rows?: number;
  applied_filters?: Record<string, string>;
  kpis?: Record<string, number | null> | null;
  dimensions?: Record<string, boolean>;
  filters: { category: string[]; city: string[]; region: string[] };
  monthly: { date: string; sales: number; profit: number }[];
  categories: DimensionRow[];
  products: DimensionRow[];
  cities: DimensionRow[];
  regions: DimensionRow[];
  category_month: { label: string; date: string; sales: number; profit: number }[];
  category_city: HeatmapRow[];
  region_month: { label: string; date: string; sales: number; profit: number }[];
  product_category: { product_name: string; category: string; sales: number; profit: number }[];
  histogram: { sales: HistogramBin[]; profit: HistogramBin[] };
  box: { sales_by_category: BoxSummary[]; profit_by_category: BoxSummary[] };
  scatter: { sales: number; profit: number; category?: string | null; city?: string | null; product_name?: string | null }[];
  pareto: ParetoRow[];
  waterfall: WaterfallRow[];
  funnel: FunnelStage[];
  decomposition: DecompositionNode;
  influencers: InfluencerRow[];
  notes: string[];
};

export type VisualFilters = {
  dateFrom: string;
  dateTo: string;
  category: string;
  city: string;
  region: string;
};

export const EMPTY_FILTERS: VisualFilters = { dateFrom: "", dateTo: "", category: "", city: "", region: "" };

export function visualEndpoint(datasetId: string, filters: VisualFilters): string {
  const params = new URLSearchParams();
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.category) params.set("category", filters.category);
  if (filters.city) params.set("city", filters.city);
  if (filters.region) params.set("region", filters.region);
  const query = params.toString();
  return `/api/retailmind/visuals/${encodeURIComponent(datasetId)}${query ? `?${query}` : ""}`;
}

export async function fetchVisuals(url: string): Promise<VisualPayload> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch(url, { cache: "no-store", signal: controller.signal });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Could not load visual analytics.");
    return payload as VisualPayload;
  } catch (reason) {
    if (reason instanceof DOMException && reason.name === "AbortError") {
      throw new Error("Visual analytics took too long to respond. Please retry.");
    }
    throw reason;
  }
  finally {
    clearTimeout(timer);
  }
}

export function downloadRowsCsv(filename: string, rows: Record<string, unknown>[]) {
  if (!rows.length) return;
  const headers = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  const escape = (value: unknown) => {
    const text = value == null ? "" : String(value);
    return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
  };
  const csv = [headers.join(","), ...rows.map((row) => headers.map((header) => escape(row[header])).join(","))].join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
