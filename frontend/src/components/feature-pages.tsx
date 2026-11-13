"use client";

import { useRef, useState, type ChangeEvent, type DragEvent, type FormEvent, type ReactNode } from "react";
import { AnalyticsDateFilter } from "@/components/analytics-date-filter";
import { useChartAnimation, useAnimationPreference } from "@/lib/animation-preference";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { formatCompactCurrency, formatCurrency, formatCurrencyPrecise, formatDate, formatNumber, formatPercent } from "@/lib/format";
import useSWR, { useSWRConfig } from "swr";
import Link from "next/link";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { useDataset, useSession, type ActiveDataset } from "@/components/providers";
import {
  Activity,
  ArrowRight,
  Bot,
  Check,
  CircleAlert,
  CloudUpload,
  Database,
  FileBarChart2,
  FileSpreadsheet,
  FileText,
  Lightbulb,
  LockKeyhole,
  PackageSearch,
  RefreshCw,
  Search,
  ShieldCheck,
  Target,
  Sparkles,
  Wrench,
  Users,
} from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { NavigationItem } from "@/lib/navigation";

function FeatureLoading() {
  return <div className="loading-panel" aria-live="polite" aria-busy="true" />;
}

// Expensive visual modules load only on the routes that use them.
const VisualAnalyticsPage = dynamic(
  () => import("@/components/visual-analytics").then((module) => module.VisualAnalyticsPage),
  { ssr: false, loading: FeatureLoading },
);
const IndiaMapPage = dynamic(
  () => import("@/components/india-map").then((module) => module.IndiaMapPage),
  { ssr: false, loading: FeatureLoading },
);
const CityAnalyticsPage = dynamic(
  () => import("@/components/city-analytics").then((module) => module.CityAnalyticsPage),
  { ssr: false, loading: FeatureLoading },
);

function PageHeading({ item }: { item: NavigationItem }) {
  const Icon = item.icon;
  return (
    <section className="page-heading-row">
      <div>
        <div className="heading-kicker"><span className="heading-icon"><Icon aria-hidden="true" /></span><span>{item.label}</span></div>
        <h1 className="page-title">{item.label}</h1>
        <p className="page-description">{item.description}</p>
      </div>
      <Badge variant="outline" className="status-badge">Python API · account-scoped</Badge>
    </section>
  );
}

function EmptyState({
  icon: Icon = Database,
  title,
  description,
  action,
  href = "/upload",
}: {
  icon?: typeof Database;
  title: string;
  description: string;
  action?: string;
  href?: string;
}) {
  return (
    <div className="feature-empty" role="status">
      <span className="feature-empty-icon"><Icon aria-hidden="true" /></span>
      <h3>{title}</h3>
      <p>{description}</p>
      {action ? <Link href={href} className={cn(buttonVariants({ variant: "outline", size: "sm" }), "empty-action")}>{action}<ArrowRight aria-hidden="true" /></Link> : null}
    </div>
  );
}

function DatasetPage({ item }: { item: NavigationItem }) {
  const { dataset, datasets, datasetsLoading, refreshDatasets, setDataset, resetDatasetSelection } = useDataset();
  const [query, setQuery] = useState("");
  const [message, setMessage] = useState("");
  const [messageIsError, setMessageIsError] = useState(false);
  const filteredDatasets = datasets.filter((entry) => entry.filename.toLowerCase().includes(query.trim().toLowerCase()));

  async function activateDataset(id: string) {
    setMessage("");
    try {
      const response = await fetch(`/api/retailmind/datasets/${encodeURIComponent(id)}`, { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Could not load this dataset.");
      setDataset({ id: payload.dataset_id, filename: payload.filename, uploadedAt: payload.created_at ?? "", rows: payload.row_count, columns: payload.columns, preview: payload.preview, mapping: payload.mapping, profile: payload.profile, quality: payload.quality });
      setMessage(`${payload.filename} is now the active dataset.`);
      setMessageIsError(false);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Could not load this dataset.");
      setMessageIsError(true);
    }
  }

  async function deleteDataset(id: string, filename: string) {
    if (!window.confirm(`Delete ${filename} and its stored upload?`)) return;
    setMessage("");
    try {
      const response = await fetch(`/api/retailmind/datasets/${encodeURIComponent(id)}`, { method: "DELETE" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Could not delete this dataset.");
      await refreshDatasets();
      if (dataset?.id === id) resetDatasetSelection();
      setMessage(`${filename} was deleted.`);
      setMessageIsError(false);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Could not delete this dataset.");
      setMessageIsError(true);
    }
  }

  return (
    <div className="page-stack">
      <PageHeading item={item} />
      <Card className="panel-card">
        <CardHeader className="panel-header">
          <div><CardTitle className="panel-title">Your datasets</CardTitle><p className="panel-subtitle">Saved files are scoped to your account and stored outside the public web root.</p></div>
          <Link href="/upload" className={cn(buttonVariants({ size: "sm" }), "action-button")}><CloudUpload data-icon="inline-start" /> Upload dataset</Link>
        </CardHeader>
        <CardContent>
          <div className="dataset-toolbar"><label htmlFor="dataset-search">Find a dataset</label><div className="dataset-search-wrap"><Search aria-hidden="true" /><Input id="dataset-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search file names" /></div><span>{datasets.length} saved</span></div>
          {message ? <p className={cn("upload-message", messageIsError && "upload-message-error")} role={messageIsError ? "alert" : "status"}>{message}</p> : null}
          <div className="table-wrap">
            <Table>
              <TableHeader><TableRow><TableHead>Dataset</TableHead><TableHead>Type</TableHead><TableHead>Records</TableHead><TableHead>Uploaded</TableHead><TableHead>Status</TableHead><TableHead className="text-right">Actions</TableHead></TableRow></TableHeader>
              <TableBody>
                {filteredDatasets.map((entry) => <TableRow key={entry.id}><TableCell><strong>{entry.filename}</strong></TableCell><TableCell>{entry.file_type.toUpperCase()}</TableCell><TableCell>{entry.rows.toLocaleString()}</TableCell><TableCell>{entry.created_at ? new Date(entry.created_at).toLocaleDateString() : "—"}</TableCell><TableCell>{dataset?.id === entry.id ? <Badge variant="secondary">Active</Badge> : <Badge variant="outline">Saved</Badge>}</TableCell><TableCell className="text-right"><div className="dataset-actions"><Button variant="outline" size="sm" disabled={dataset?.id === entry.id} onClick={() => activateDataset(entry.id)}>{dataset?.id === entry.id ? "Active" : "Open"}</Button><Button variant="ghost" size="sm" aria-label={`Delete ${entry.filename}`} onClick={() => deleteDataset(entry.id, entry.filename)}>Delete</Button></div></TableCell></TableRow>)}
                {!datasetsLoading && !filteredDatasets.length ? <TableRow><TableCell colSpan={6} className="table-empty-cell"><EmptyState icon={Database} title={query ? "No matching datasets" : "No saved datasets yet"} description={query ? "Try another file name or clear the search." : "Upload a file to save it to your account and return to it later."} action={query ? undefined : "Go to data upload"} /></TableCell></TableRow> : null}
              </TableBody>
            </Table>
          </div>
          {datasetsLoading ? <div className="loading-panel" aria-label="Loading saved datasets" /> : null}
        </CardContent>
      </Card>
      <div className="info-grid info-grid-three">
        <InfoCard icon={Check} title="Safe processing" text="The existing Python upload pipeline remains the source of truth." />
        <InfoCard icon={ShieldCheck} title="Private files" text="Upload bytes stay in user-scoped server storage; MySQL stores only metadata." />
        <InfoCard icon={RefreshCw} title="Resumable analysis" text="Your saved file can be reloaded into the Python analytics engine after a service restart." />
      </div>
    </div>
  );
}

type UploadResponse = {
  dataset_id: string;
  filename: string;
  row_count: number;
  columns: string[];
  preview: ActiveDataset["preview"];
  mapping: ActiveDataset["mapping"];
  profile: ActiveDataset["profile"];
  quality: ActiveDataset["quality"];
};
type UploadHistoryRow = { original_filename: string; file_type: string; uploaded_at: string; row_count: number; upload_status: string; validation_status: string };
type CleaningSuggestion = { key: string; column: string; issue: string; count: number; action: string; default: boolean; risk: string; sample: string[] };
type CleaningReview = {
  columns: string[];
  domain_label: string;
  options: Record<string, boolean>;
  suggestions: CleaningSuggestion[];
  preview: ActiveDataset["preview"];
  report: { rows_before: number; rows_after: number; applied: Record<string, number>; warnings: string[]; original_preserved: boolean };
  original_preserved: boolean;
};

const MAPPING_LABELS: Record<string, string> = {
  order_id: "Order ID", order_date: "Order date", category: "Category", product_name: "Product",
  city: "City", region: "Region", sales_rep: "Sales representative", payment_method: "Payment method",
  sales: "Sales / revenue", profit: "Profit", quantity: "Quantity", unit_price: "Unit price",
  customer: "Customer", discount: "Discount",
};
const CLEANING_LABELS: Record<string, string> = {
  trim_whitespace: "Trim and collapse whitespace",
  normalise_categories: "Normalize category spelling",
  parse_dates: "Parse recognized date columns",
  coerce_numerics: "Convert recognized measures to numbers",
  drop_duplicate_rows: "Remove exact duplicate rows",
  drop_empty_rows: "Remove completely empty rows",
  fill_invalid_numeric_zero: "Replace invalid numbers with zero",
};

function UploadPage({ item }: { item: NavigationItem }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();
  const { dataset, setDataset, refreshDatasets } = useDataset();
  const { data: historyData, error: historyError, isLoading: historyLoading, mutate: refreshHistory } = useSWR<{ history: UploadHistoryRow[] }>("/api/retailmind/datasets/history", fetchJson);
  const { data: cleaningReview, error: cleaningReviewError, isLoading: cleaningReviewLoading, mutate: refreshCleaningReview } = useSWR<CleaningReview>(dataset ? `/api/retailmind/datasets/${encodeURIComponent(dataset.id)}/cleaning` : null, fetchJson);
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState("");
  const [messageIsError, setMessageIsError] = useState(false);
  const [mappingDrafts, setMappingDrafts] = useState<Record<string, Record<string, string | null>>>({});
  const [mappingSaving, setMappingSaving] = useState(false);
  const [reviewMessage, setReviewMessage] = useState("");
  const [reviewMessageIsError, setReviewMessageIsError] = useState(false);
  const [cleaningSelections, setCleaningSelections] = useState<Record<string, Record<string, boolean>>>({});
  const [cleaningExporting, setCleaningExporting] = useState(false);

  const mappingDraft = dataset ? mappingDrafts[dataset.id] ?? dataset.mapping : {};
  const cleaningOptions = dataset ? cleaningSelections[dataset.id] ?? cleaningReview?.options ?? {} : {};

  function acceptFile(candidate?: File) {
    if (!candidate) return;
    const validExtension = /\.(csv|xlsx|xls|xlsm)$/i.test(candidate.name);
    if (!validExtension) {
      setFile(null);
      setMessage("Choose a CSV or Excel workbook (.csv, .xlsx, .xls, .xlsm).");
      setMessageIsError(true);
      return;
    }
    if (candidate.size > 25 * 1024 * 1024) {
      setFile(null);
      setMessage("This file is larger than the existing 25 MB upload limit.");
      setMessageIsError(true);
      return;
    }
    setFile(candidate);
    setProgress(0);
    setMessage("File selected and ready for server-side validation and account storage.");
    setMessageIsError(false);
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    acceptFile(event.target.files?.[0]);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    acceptFile(event.dataTransfer.files?.[0]);
  }

  function updateMapping(field: string, column: string) {
    if (!dataset) return;
    setMappingDrafts((current) => ({
      ...current,
      [dataset.id]: { ...mappingDraft, [field]: column || null },
    }));
  }

  async function saveMapping() {
    if (!dataset || mappingSaving) return;
    setMappingSaving(true);
    setReviewMessage("");
    try {
      const response = await fetch(`/api/retailmind/datasets/${encodeURIComponent(dataset.id)}/mapping`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ mapping: mappingDraft }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "The field mapping could not be saved.");
      const updatedMapping = payload.mapping as ActiveDataset["mapping"];
      setMappingDrafts((current) => ({ ...current, [dataset.id]: updatedMapping }));
      setDataset({ ...dataset, mapping: updatedMapping });
      setReviewMessage("Mapping updated for this API session. The original upload is unchanged; mappings are not yet stored in MySQL.");
      setReviewMessageIsError(false);
    } catch (reason) {
      setReviewMessage(reason instanceof Error ? reason.message : "The field mapping could not be saved.");
      setReviewMessageIsError(true);
    } finally {
      setMappingSaving(false);
    }
  }

  function updateCleaningOption(option: string, checked: boolean) {
    if (!dataset) return;
    setCleaningSelections((current) => ({
      ...current,
      [dataset.id]: { ...(current[dataset.id] ?? cleaningReview?.options ?? {}), [option]: checked },
    }));
  }

  async function downloadCleanedCopy() {
    if (!dataset || cleaningExporting) return;
    setCleaningExporting(true);
    setReviewMessage("");
    try {
      const response = await fetch(`/api/retailmind/datasets/${encodeURIComponent(dataset.id)}/cleaning`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ options: cleaningOptions }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || "The cleaned copy could not be created.");
      }
      const report = JSON.parse(response.headers.get("x-cleaning-report") || "{}") as {
        rows_before?: number; rows_after?: number; applied?: Record<string, number>; warnings?: string[];
      };
      const blob = await response.blob();
      const href = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = href;
      anchor.download = response.headers.get("content-disposition")?.match(/filename="([^"]+)"/)?.[1] || "cleaned-dataset.csv";
      anchor.click();
      URL.revokeObjectURL(href);
      await refreshCleaningReview();
      const appliedCount = Object.values(report.applied ?? {}).reduce((sum, value) => sum + value, 0);
      setReviewMessage(`Downloaded a cleaned copy (${report.rows_after ?? report.rows_before ?? dataset.rows} rows; ${appliedCount} reported changes). The original upload remains untouched.${report.warnings?.length ? ` ${report.warnings.join(" ")}` : ""}`);
      setReviewMessageIsError(false);
    } catch (reason) {
      setReviewMessage(reason instanceof Error ? reason.message : "The cleaned copy could not be created.");
      setReviewMessageIsError(true);
    } finally {
      setCleaningExporting(false);
    }
  }

  async function processFile() {
    if (!file || uploading) return;
    setUploading(true);
    setProgress(0);
    setMessage("Uploading and profiling your dataset with the Python backend…");
    setMessageIsError(false);
    const formData = new FormData();
    formData.append("file", file);
    try {
      const result = await new Promise<UploadResponse>((resolve, reject) => {
        const request = new XMLHttpRequest();
        request.open("POST", "/api/retailmind/upload");
        request.upload.onprogress = (event) => {
          if (event.lengthComputable) setProgress(Math.round((event.loaded / event.total) * 100));
        };
        request.onload = () => {
          let payload: UploadResponse & { detail?: string };
          try { payload = JSON.parse(request.responseText) as UploadResponse & { detail?: string }; }
          catch { reject(new Error("The Python API returned an unreadable response.")); return; }
          if (request.status < 200 || request.status >= 300) {
            reject(new Error(payload.detail || "The Python API could not process this file."));
            return;
          }
          resolve(payload);
        };
        request.onerror = () => reject(new Error("The Python API could not be reached."));
        request.onabort = () => reject(new Error("The upload was cancelled."));
        request.send(formData);
      });
      setProgress(100);
      setDataset({ id: result.dataset_id, filename: result.filename, uploadedAt: new Date().toISOString(), rows: result.row_count, columns: result.columns, preview: result.preview, mapping: result.mapping, profile: result.profile, quality: result.quality });
      await Promise.all([refreshDatasets(), refreshHistory()]);
      const salesDetected = Boolean(result.mapping.sales);
      setMessage(salesDetected
        ? "Dataset processed and saved to your account."
        : "The file was uploaded, but no Sales/Revenue column was detected. Map the Sales column below and apply the mapping to continue.");
      setMessageIsError(!salesDetected);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      if (salesDetected) router.push("/overview");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The Python API could not process this file.");
      setMessageIsError(true);
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="page-stack">
      <PageHeading item={item} />
      <div className="upload-layout">
        <Card className="panel-card upload-card">
          <CardHeader>
            <CardTitle className="panel-title">Upload a dataset</CardTitle>
            <p className="panel-subtitle">CSV and Excel files up to 25 MB are supported by the existing backend.</p>
          </CardHeader>
          <CardContent>
            <input ref={inputRef} className="sr-only" type="file" accept=".csv,.xlsx,.xls,.xlsm,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel,application/vnd.ms-excel.sheet.macroEnabled.12" aria-label="Choose a CSV or Excel dataset" onChange={handleFileChange} />
            <div
              className={cn("upload-dropzone", dragging && "upload-dropzone-active")}
              role="button"
              tabIndex={0}
              aria-label="Choose or drop a CSV or Excel dataset"
              onClick={() => inputRef.current?.click()}
              onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); inputRef.current?.click(); } }}
              onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={handleDrop}
            >
              <span className="upload-icon"><CloudUpload aria-hidden="true" /></span>
              <strong>Drop your file here, or <span>browse</span></strong>
              <span className="upload-hint">CSV, XLS, XLSX, or XLSM · maximum 25 MB</span>
            </div>
            {file ? (
              <div className="selected-file">
                <span className="file-type-icon"><FileSpreadsheet aria-hidden="true" /></span>
                <div className="selected-file-copy"><strong>{file.name}</strong><span>{(file.size / 1024 / 1024).toFixed(2)} MB · selected locally</span></div>
                <Button variant="ghost" size="sm" onClick={() => { setFile(null); setMessage(""); if (inputRef.current) inputRef.current.value = ""; }}>Remove</Button>
              </div>
            ) : null}
            {message ? <p className={cn("upload-message", messageIsError && "upload-message-error")} role={messageIsError ? "alert" : "status"}>{message}</p> : null}
            {uploading ? <div className="upload-progress" role="progressbar" aria-label="Dataset upload progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}><div><span style={{ width: `${progress}%` }} /></div><span>{progress}% uploaded</span></div> : null}
            <div className="upload-footer">
              <p><LockKeyhole aria-hidden="true" /> Python validates files; bytes are stored outside the public web root.</p>
              <Button disabled={!file || uploading} onClick={processFile} title={!file ? "Choose a file before processing" : undefined}>{uploading ? "Processing…" : "Process dataset"}</Button>
            </div>
            <div className="backend-notice"><CircleAlert aria-hidden="true" /><span><strong>Account-scoped storage.</strong> The original file and metadata persist per user. Parsed frames are cached for analysis and can be reloaded after an API restart.</span></div>
          </CardContent>
        </Card>
        <Card className="panel-card upload-checklist">
          <CardHeader><CardTitle className="panel-title">What happens next</CardTitle><p className="panel-subtitle">A transparent review before analysis.</p></CardHeader>
          <CardContent>
            <ol className="steps-list">
              <li><span>01</span><div><strong>Inspect columns</strong><p>Detect dates, measures, dimensions, and likely field mappings.</p></div></li>
              <li><span>02</span><div><strong>Review data quality</strong><p>See missing values and safe cleaning suggestions before applying them.</p></div></li>
              <li><span>03</span><div><strong>Build your workspace</strong><p>Use the existing Python analytics engine to create reports and insights.</p></div></li>
            </ol>
            <Link href="/data-connections" className="text-action">View backend connection details <ArrowRight aria-hidden="true" /></Link>
          </CardContent>
        </Card>
      </div>
      {dataset ? <Card className="panel-card"><CardHeader className="panel-header"><div><CardTitle className="panel-title">Dataset review</CardTitle><p className="panel-subtitle">Column detection and data-quality checks from the Python parser; no data is changed during review.</p></div><Badge variant="secondary">{dataset.filename}</Badge></CardHeader><CardContent><div className="metric-grid metric-grid-three">{[{ label: "Missing cells", value: dataset.quality.missing_cells }, { label: "Columns with gaps", value: dataset.quality.columns_with_missing_values }, { label: "Duplicate rows", value: dataset.quality.duplicate_rows }].map((metric) => <div className="metric-card" key={metric.label}><div className="metric-content"><span className="metric-label">{metric.label}</span><span className="metric-value">{metric.value.toLocaleString()}</span></div></div>)}</div><div className="backend-contract"><span>Detected columns</span><code>{dataset.columns.join(" · ")}</code></div><div className="backend-contract"><span>Suggested field mapping</span><code>{Object.entries(dataset.mapping).filter(([, value]) => value).map(([field, value]) => `${field.replaceAll("_", " ")} → ${value}`).join(" · ") || "No standard retail fields detected"}</code></div><div className="table-wrap"><Table><TableHeader><TableRow>{dataset.columns.map((column) => <TableHead key={column}>{column}</TableHead>)}</TableRow></TableHeader><TableBody>{dataset.preview.map((row, index) => <TableRow key={index}>{dataset.columns.map((column) => <TableCell key={column}>{String(row[column] ?? "—")}</TableCell>)}</TableRow>)}</TableBody></Table></div></CardContent></Card> : null}
      {dataset ? (
        <div className="review-tools-grid">
          <Card className="panel-card">
            <CardHeader><CardTitle className="panel-title">Review field mapping</CardTitle><p className="panel-subtitle">Correct detected retail fields before using analytics. Changes are held in the API process, not written to MySQL.</p></CardHeader>
            <CardContent>
              <div className="mapping-grid">
                {Object.keys(dataset.mapping).map((field) => (
                  <label className="mapping-field" key={field}>
                    <span>{MAPPING_LABELS[field] ?? field.replaceAll("_", " ")}</span>
                    <select aria-label={`${MAPPING_LABELS[field] ?? field.replaceAll("_", " ")} source column`} value={mappingDraft[field] ?? ""} onChange={(event) => updateMapping(field, event.target.value)}>
                      <option value="">Not mapped</option>
                      {dataset.columns.map((column) => <option key={column} value={column}>{column}</option>)}
                    </select>
                  </label>
                ))}
              </div>
              <Button type="button" size="sm" disabled={mappingSaving} onClick={saveMapping}>{mappingSaving ? "Saving…" : "Apply field mapping"}</Button>
            </CardContent>
          </Card>
          <Card className="panel-card">
            <CardHeader><CardTitle className="panel-title">Safe cleaning review</CardTitle><p className="panel-subtitle">Review factual suggestions, then download a separate cleaned CSV. The original upload is never modified.</p></CardHeader>
            <CardContent>
              {cleaningReviewError ? <p className="assistant-error" role="alert">{cleaningReviewError.message}</p> : null}
              {cleaningReviewLoading ? <div className="loading-panel" aria-label="Analyzing cleaning suggestions" /> : null}
              {cleaningReview ? <>
                {cleaningReview.suggestions.length ? <ul className="cleaning-suggestions">{cleaningReview.suggestions.map((suggestion) => <li key={suggestion.key}><div><strong>{suggestion.issue}</strong><span>{suggestion.column} · {suggestion.count.toLocaleString()} affected</span></div><p>{suggestion.action}</p></li>)}</ul> : <p className="cleaning-empty">No cleaning issues were detected by the current checks.</p>}
                <fieldset className="cleaning-options">
                  <legend>Choose transformations</legend>
                  {Object.entries(cleaningReview.options).map(([option, defaultValue]) => (
                    <label key={option}>
                      <input type="checkbox" checked={cleaningOptions[option] ?? defaultValue} onChange={(event) => updateCleaningOption(option, event.target.checked)} />
                      <span>{option === "fill_invalid_numeric_zero" ? "Replace invalid numbers with zero (may distort totals)" : CLEANING_LABELS[option] ?? option}</span>
                    </label>
                  ))}
                </fieldset>
                <Button type="button" size="sm" disabled={cleaningExporting} onClick={downloadCleanedCopy}>{cleaningExporting ? "Preparing copy…" : "Download cleaned CSV"}</Button>
              </> : null}
            </CardContent>
          </Card>
        </div>
      ) : null}
      {reviewMessage ? <p className={cn("upload-message", reviewMessageIsError && "upload-message-error")} role={reviewMessageIsError ? "alert" : "status"}>{reviewMessage}</p> : null}
      <Card className="panel-card">
        <CardHeader className="panel-header"><div><CardTitle className="panel-title">Upload history</CardTitle><p className="panel-subtitle">Recent validations recorded to your account.</p></div><Badge variant="secondary">{historyData?.history.length ?? 0} records</Badge></CardHeader>
        <CardContent>{historyError ? <p className="assistant-error" role="alert">{historyError.message}</p> : null}{historyLoading ? <div className="loading-panel" aria-label="Loading upload history" /> : historyData?.history.length ? <div className="table-wrap"><Table><TableHeader><TableRow><TableHead>File</TableHead><TableHead>Uploaded</TableHead><TableHead>Rows</TableHead><TableHead>Validation</TableHead><TableHead>Status</TableHead></TableRow></TableHeader><TableBody>{historyData.history.map((entry, index) => <TableRow key={`${entry.original_filename}-${entry.uploaded_at}-${index}`}><TableCell>{entry.original_filename}</TableCell><TableCell>{entry.uploaded_at ? new Date(entry.uploaded_at).toLocaleString() : "—"}</TableCell><TableCell>{Number(entry.row_count).toLocaleString()}</TableCell><TableCell>{entry.validation_status}</TableCell><TableCell>{entry.upload_status}</TableCell></TableRow>)}</TableBody></Table></div> : <EmptyState icon={Activity} title="No uploads yet" description="Processed datasets will appear here after the first successful upload." />}</CardContent>
      </Card>
    </div>
  );
}

function ActivityPage({ item }: { item: NavigationItem }) {
  const { data, error, isLoading } = useSWR<{ history: UploadHistoryRow[] }>("/api/retailmind/datasets/history", fetchJson);
  return <div className="page-stack"><PageHeading item={item} /><Card className="panel-card"><CardHeader className="panel-header"><div><CardTitle className="panel-title">Recent workspace activity</CardTitle><p className="panel-subtitle">Upload events from your account history.</p></div><Link href="/datasets" className="panel-link">Manage datasets <ArrowRight aria-hidden="true" /></Link></CardHeader><CardContent>{error ? <p className="assistant-error" role="alert">{error.message}</p> : null}{isLoading ? <div className="loading-panel" aria-label="Loading recent activity" /> : data?.history.length ? <div className="activity-list">{data.history.map((entry, index) => <article className="activity-row" key={`${entry.original_filename}-${entry.uploaded_at}-${index}`}><span className="file-type-icon"><Activity aria-hidden="true" /></span><div><strong>Dataset processed: {entry.original_filename}</strong><span>{Number(entry.row_count).toLocaleString()} rows · {entry.validation_status} · {entry.upload_status}</span></div><time dateTime={entry.uploaded_at}>{entry.uploaded_at ? new Date(entry.uploaded_at).toLocaleString() : "—"}</time></article>)}</div> : <EmptyState icon={Activity} title="Your workspace is quiet" description="Upload a dataset to record your first activity item." action="Import data" />}</CardContent></Card></div>;
}

type AnalysisRow = Record<string, string | number | boolean | null>;
type AnalysisResult = { available: boolean; rows?: AnalysisRow[]; recommendations?: AnalysisRow[]; notes?: string[]; assumptions?: string[]; stock_available?: boolean };
type AlertPreferences = { enabled: boolean; configured: boolean; smtp_ready: boolean; min_severity: "critical" | "warning" | "info"; frequency: "instant" | "daily"; recipient_count: number; missing: string[] };

type IntelligenceResult = {
  available: boolean;
  insights?: string[];
  alerts?: {
    id?: string; title: string; description: string; severity: string; suggestion: string; metric: string;
    status?: "new" | "acknowledged" | "dismissed" | "resolved"; current_value?: number | null; previous_value?: number | null;
    pct_change?: number | null; comparison_period?: string; scope?: string; evidence?: Record<string, unknown>;
    acknowledged_at?: string | null; detected_at?: string; severity_label?: string; scope_label?: string; scope_dimension?: string;
  }[];
  email?: { enabled: boolean; configured: boolean; status: string; missing?: string[]; sent?: { alert_id: string; title: string; delivery: string }[]; failed?: { alert_id: string; title: string; delivery: string }[] };
  summary?: AnalysisRow[];
  customers?: AnalysisRow[];
  customer_total?: number;
  customer_offset?: number;
  customer_limit?: number;
  cluster_count?: number;
  silhouette?: number | null;
  tags?: Record<string, number>;
  tag_total?: number;
  notes?: string[];
}

const TAG_CLASSES: Record<string, string> = {
  VIP: "tag-vip",
  Loyal: "tag-loyal",
  New: "tag-new",
  Regular: "tag-regular",
  "At Risk": "tag-at-risk",
  Lost: "tag-lost",
};

function TagBadge({ tag }: { tag: string }) {
  return <span className={`tag-badge ${TAG_CLASSES[tag] ?? "tag-regular"}`}>{tag}</span>;
}

const SEGMENT_GUIDANCE: Record<string, string> = {
  "Big Spenders": "High monetary value. Protect with loyalty perks and early access rather than blanket discounts.",
  "Loyal Customers": "Consistent repeat buyers. Grow basket size with cross-sell and referral offers.",
  "Potential Loyalists": "Recent repeat activity. Nurture with a second-purchase incentive.",
  "New Customers": "First purchase only. Onboard quickly and measure the second-order conversion.",
  "At-Risk Customers": "Previously valuable but inactive. Run a win-back campaign before they lapse.",
  "Churn Risk Customers": "Low recency and frequency. Prioritise reactivation or accept controlled attrition.",
};;

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: "no-store" });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "Could not load this analysis.");
  return payload as T;
}

const fetchAnalysis = (url: string) => fetchJson<AnalysisResult>(url);

function downloadFromUrl(url: string) {
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "";
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
}

function downloadRowsAsCsv(filename: string, rows: Record<string, unknown>[]) {
  if (!rows.length) return;
  const columns = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  const quote = (value: unknown) => {
    const text = value == null ? "" : String(value);
    const safeText = typeof value === "string" && /^[\t\r ]*[=+\-@]/.test(text) ? `'${text}` : text;
    return `"${safeText.replaceAll('"', '""')}"`;
  };
  const csv = [columns.map(quote).join(","), ...rows.map((row) => columns.map((column) => quote(row[column])).join(","))].join("\r\n");
  const href = URL.createObjectURL(new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(href), 0);
}

const forecastChartConfig = {
  actual: { label: "Actual", color: "var(--chart-1)" },
  forecast: { label: "Forecast", color: "var(--chart-2)" },
  lower_bound: { label: "Lower bound", color: "var(--chart-3)" },
  upper_bound: { label: "Upper bound", color: "var(--chart-3)" },
} satisfies ChartConfig;

function AnalyticsPage({ item }: { item: NavigationItem }) {
  const { dataset } = useDataset();
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const inventory = item.href === "/inventory-analytics";
  const dimension = item.href === "/sales-analytics" ? "month" : item.href === "/profitability-analytics" || item.href === "/category-analytics" ? "category" : item.href === "/product-analytics" ? "product_name" : item.href === "/city-analytics" ? "city" : "customer";
  const baseEndpoint = inventory ? `/api/retailmind/inventory/${encodeURIComponent(dataset?.id ?? "")}` : `/api/retailmind/analytics/${encodeURIComponent(dataset?.id ?? "")}/${dimension}`;
  const dateParams = new URLSearchParams();
  if (dateFrom) dateParams.set("date_from", dateFrom);
  if (dateTo) dateParams.set("date_to", dateTo);
  const query = dateParams.toString();
  const endpoint = dataset ? `${baseEndpoint}${query ? `?${query}` : ""}` : null;
  const { data, error, isLoading } = useSWR<AnalysisResult>(endpoint, fetchAnalysis);
  const rows = inventory ? data?.recommendations ?? [] : data?.rows ?? [];
  const { isAnimationActive, animationDuration, animationEasing } = useChartAnimation();
  const fields = rows.length ? Object.keys(rows[0]) : [];
  const labelField = fields[0];
  const preferredMetricFields = ["sales", "revenue", "recommended_order_quantity", "profit", "quantity"];
  const chartField = preferredMetricFields.find((field) => fields.includes(field))
    ?? fields.find((field) => typeof rows[0]?.[field] === "number");
  const chartRows = chartField
    ? rows.filter((row) => typeof row[chartField] === "number").slice(0, 8).map((row) => ({
        label: String(row[labelField] ?? "—").slice(0, 30),
        value: Number(row[chartField]),
      }))
    : [];
  const salesField = fields.includes("sales") ? "sales" : fields.includes("revenue") ? "revenue" : null;
  const totalSales = salesField
    ? rows.reduce((sum, row) => {
        const value = row[salesField];
        return sum + (typeof value === "number" ? value : 0);
      }, 0)
    : null;
  const marginValues = rows
    .map((row) => row.margin)
    .filter((value): value is number => typeof value === "number");
  const averageMargin = marginValues.length ? marginValues.reduce((sum, value) => sum + value, 0) / marginValues.length : null;
  const totalRecommended = fields.includes("recommended_order_quantity")
    ? rows.reduce((sum, row) => {
        const value = row.recommended_order_quantity;
        return sum + (typeof value === "number" ? value : 0);
      }, 0)
    : null;

  function formatCell(key: string, value: string | number | boolean | null) {
    if (value == null) return "—";
    if (typeof value === "boolean") return value ? "Yes" : "No";
    if (typeof value === "number" && ["sales", "profit", "revenue", "monetary_value", "average_purchase_value", "reorder_point", "recommended_order_quantity"].includes(key)) {
      return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(value);
    }
    if (typeof value === "number" && ["margin", "revenue_share", "customer_share"].includes(key)) return `${(value * 100).toFixed(1)}%`;
    if (key === "date" && typeof value === "string") return new Date(value).toLocaleDateString();
    return typeof value === "number" ? new Intl.NumberFormat("en-IN", { maximumFractionDigits: 1 }).format(value) : value;
  }

  return (
    <div className="page-stack">
      <PageHeading item={item} />
      <div className="filter-row">
        <span className="filter-note"><Database aria-hidden="true" /> {dataset ? `${dataset.filename} · ${dataset.rows.toLocaleString()} source rows` : "Select a dataset to calculate this view"}</span>
        <AnalyticsDateFilter
          dateFrom={dateFrom}
          dateTo={dateTo}
          disabled={!dataset}
          onDateFromChange={setDateFrom}
          onDateToChange={setDateTo}
          onClear={() => { setDateFrom(""); setDateTo(""); }}
        />
      </div>
      {!dataset ? <EmptyState icon={Database} title="Choose a dataset to begin" description="Upload a CSV or Excel file to see analysis calculated from your data." action="Upload a dataset" /> : null}
      {isLoading ? <div className="loading-panel" aria-live="polite" /> : null}
      {error ? <p className="assistant-error" role="alert">{error.message}</p> : null}
      {data && !data.available ? <div className="backend-notice" role="status"><CircleAlert aria-hidden="true" /><span>{data.notes?.join(" ") || "This analysis is not available for the uploaded dataset."}</span></div> : null}
      {data?.available && rows.length ? (
        <section className="analytics-summary" aria-label="Calculated summary">
          <Card className="metric-card"><CardContent className="metric-content"><div className="metric-topline"><span className="metric-label">{inventory ? "Recommendations" : "Groups returned"}</span><span className="metric-icon"><Database aria-hidden="true" /></span></div><div className="metric-value"><AnimatedNumber value={rows.length} format={(value) => formatNumber(value, 0)} /></div><div className="metric-footnote">From the existing analytics engine</div></CardContent></Card>
          <Card className="metric-card"><CardContent className="metric-content"><div className="metric-topline"><span className="metric-label">{inventory ? "Recommended units" : salesField === "revenue" ? "Total revenue" : "Total sales"}</span><span className="metric-icon"><FileBarChart2 aria-hidden="true" /></span></div><div className="metric-value"><AnimatedNumber value={inventory ? totalRecommended : totalSales} format={(value) => formatCompactCurrency(value)} /></div><div className="metric-footnote">Aggregated from the returned rows</div></CardContent></Card>
          <Card className="metric-card"><CardContent className="metric-content"><div className="metric-topline"><span className="metric-label">{inventory ? "Average recommendation" : "Average margin"}</span><span className="metric-icon"><Activity aria-hidden="true" /></span></div><div className="metric-value"><AnimatedNumber value={inventory ? (totalRecommended != null ? totalRecommended / Math.max(1, rows.length) : null) : (averageMargin != null ? averageMargin * 100 : null)} format={(value) => inventory ? formatNumber(value) : formatPercent(value)} /></div><div className="metric-footnote">Computed from the same response</div></CardContent></Card>
        </section>
      ) : null}
      {data?.available && rows.length && chartRows.length ? (
        <Card className="panel-card">
          <CardHeader className="panel-header"><div><CardTitle className="panel-title">Top {inventory ? "replenishment items" : "groups"} by {String(chartField).replaceAll("_", " ")}</CardTitle><p className="panel-subtitle">Top {chartRows.length} of {rows.length.toLocaleString()} rows returned by the API</p></div><Badge variant="secondary">Live dataset</Badge></CardHeader>
          <CardContent>
            <div className="analytics-chart">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart key={isAnimationActive ? "animated" : "static"} data={chartRows} layout="vertical" margin={{ top: 4, right: 16, left: 4, bottom: 4 }}>
                  <CartesianGrid stroke="#edf0f5" strokeDasharray="3 4" horizontal={false} />
                  <XAxis type="number" tickLine={false} axisLine={false} tick={{ fill: "#8993a2", fontSize: 9 }} tickFormatter={(value: number) => new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 }).format(value)} />
                  <YAxis type="category" dataKey="label" width={116} tickLine={false} axisLine={false} tick={{ fill: "#8993a2", fontSize: 8 }} />
                  <Tooltip formatter={(value) => ["sales", "revenue", "profit"].includes(String(chartField)) ? formatCurrency(Number(value)) : formatNumber(Number(value))} />
                  <Bar dataKey="value" name={String(chartField).replaceAll("_", " ")} radius={[0, 6, 6, 0]} barSize={14} isAnimationActive={isAnimationActive} animationDuration={animationDuration} animationEasing={animationEasing}>
                    {chartRows.map((row, index) => <Cell key={`${row.label}-${index}`} fill={index % 2 === 0 ? "#3e75bd" : "#a6c4f1"} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      ) : null}
      {data?.available && rows.length ? <Card className="panel-card"><CardHeader className="panel-header"><div><CardTitle className="panel-title">{inventory ? "Replenishment recommendations" : "Calculated results"}</CardTitle><p className="panel-subtitle">{rows.length.toLocaleString()} {inventory ? "recommendations" : "groups"} from the existing Python analytics engine</p></div><div className="analytics-card-actions"><Badge variant="secondary">Live dataset</Badge>{inventory ? <Button type="button" variant="outline" size="sm" onClick={() => downloadRowsAsCsv("inventory-recommendations.csv", rows)}>Download CSV</Button> : null}</div></CardHeader><CardContent><div className="table-wrap"><Table><TableHeader><TableRow>{fields.map((field) => <TableHead key={field}>{field.replaceAll("_", " ")}</TableHead>)}</TableRow></TableHeader><TableBody>{rows.slice(0, 100).map((row, index) => <TableRow key={String(row[fields[0]]) + index}>{fields.map((field) => <TableCell key={field}>{formatCell(field, row[field])}</TableCell>)}</TableRow>)}</TableBody></Table></div>{data.assumptions?.length ? <div className="inventory-assumptions">{data.assumptions.map((assumption) => <p key={assumption}>{assumption}</p>)}</div> : null}</CardContent></Card> : null}
      {data?.notes?.length ? <p className="dashboard-footnote">{data.notes.join(" ")}</p> : null}
    </div>
  );
}

function InfoCard({ icon: Icon, title, text }: { icon: typeof Check; title: string; text: string }) {
  return <Card className="info-card"><CardContent><span className="info-icon"><Icon aria-hidden="true" /></span><strong>{title}</strong><p>{text}</p></CardContent></Card>;
}

type StockColumn = { key: string; label: string; kind?: "number" | "date" };

const STOCK_COLUMNS: StockColumn[] = [
  { key: "product", label: "Product" },
  { key: "status", label: "Status" },
  { key: "current_stock", label: "Current stock", kind: "number" },
  { key: "avg_daily_sales", label: "Avg daily sales", kind: "number" },
  { key: "forecast_daily_demand", label: "Forecast daily demand", kind: "number" },
  { key: "safety_stock", label: "Safety stock", kind: "number" },
  { key: "reorder_point", label: "Reorder point", kind: "number" },
  { key: "days_remaining", label: "Days remaining", kind: "number" },
  { key: "estimated_depletion_date", label: "Est. depletion", kind: "date" },
  { key: "suggested_reorder_quantity", label: "Suggested reorder", kind: "number" },
];

function stockCellValue(value: string | number | boolean | null, kind?: StockColumn["kind"]) {
  if (value == null || value === "") return "—";
  if (kind === "number" && typeof value === "number") return formatNumber(value, 2);
  if (kind === "date" && typeof value === "string") {
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
  }
  return String(value);
}

function StockRecommendationsPage({ item }: { item: NavigationItem }) {
  const { dataset } = useDataset();
  const { isAnimationActive, animationDuration, animationEasing } = useChartAnimation();
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sortKey, setSortKey] = useState("suggested_reorder_quantity");
  const [sortDescending, setSortDescending] = useState(true);

  const params = new URLSearchParams();
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  const query = params.toString();
  const endpoint = dataset ? `/api/retailmind/inventory/${encodeURIComponent(dataset.id)}${query ? `?${query}` : ""}` : null;
  const { data, error, isLoading } = useSWR<AnalysisResult>(endpoint, fetchAnalysis);

  const rows = data?.recommendations ?? [];
  const statuses = Array.from(new Set(rows.map((row) => String(row.status ?? "")).filter(Boolean))).sort();
  const numeric = (row: AnalysisRow, key: string) => (typeof row[key] === "number" ? (row[key] as number) : null);
  const lowStockStatuses = ["Out of stock", "Critical — reorder now", "Low — reorder soon"];
  const needsReorder = rows.filter((row) => lowStockStatuses.includes(String(row.status ?? ""))).length;
  const overstocked = rows.filter((row) => String(row.status ?? "") === "Overstock — review cover").length;
  const reorderRow = (action: "reorder" | "healthy") =>
    rows.some((row) => {
      const status = String(row.status ?? "");
      if (action === "healthy") return status === "Healthy";
      return lowStockStatuses.includes(status);
    });

  const filteredRows = rows
    .filter((row) => {
      const term = search.trim().toLowerCase();
      const matchesSearch = !term || String(row.product ?? "").toLowerCase().includes(term);
      const matchesStatus = statusFilter === "all" || String(row.status ?? "") === statusFilter;
      return matchesSearch && matchesStatus;
    })
    .sort((left, right) => {
      const a = numeric(left, sortKey);
      const b = numeric(right, sortKey);
      const leftValue = a ?? Number.NEGATIVE_INFINITY;
      const rightValue = b ?? Number.NEGATIVE_INFINITY;
      return sortDescending ? rightValue - leftValue : leftValue - rightValue;
    });

  const totalSuggested = rows.reduce((sum, row) => sum + (numeric(row, "suggested_reorder_quantity") ?? 0), 0);
  const chartMetric = rows.some((row) => numeric(row, "suggested_reorder_quantity") != null)
    ? "suggested_reorder_quantity"
    : "reorder_point";
  const chartRows = [...rows]
    .filter((row) => numeric(row, chartMetric) != null)
    .sort((left, right) => (numeric(right, chartMetric) ?? 0) - (numeric(left, chartMetric) ?? 0))
    .slice(0, 10)
    .map((row) => ({ label: String(row.product ?? "—").slice(0, 26), value: numeric(row, chartMetric) ?? 0 }));

  function toggleSort(key: string) {
    if (sortKey === key) setSortDescending((value) => !value);
    else {
      setSortKey(key);
      setSortDescending(true);
    }
  }

  return (
    <div className="page-stack">
      <PageHeading item={item} />
      <div className="filter-row">
        <span className="filter-note"><Database aria-hidden="true" /> {dataset ? `${dataset.filename} · demand and reorder planning from the Python inventory engine` : "Select a dataset to calculate replenishment needs"}</span>
        <AnalyticsDateFilter
          dateFrom={dateFrom}
          dateTo={dateTo}
          disabled={!dataset}
          onDateFromChange={setDateFrom}
          onDateToChange={setDateTo}
          onClear={() => { setDateFrom(""); setDateTo(""); }}
        />
      </div>

      {!dataset ? <EmptyState icon={PackageSearch} title="Choose a dataset to begin" description="Stock recommendations need a product, a sales date, and a quantity sold. Add a current-stock column to unlock days remaining and suggested quantities." action="Upload a dataset" /> : null}
      {isLoading ? <div className="loading-panel" aria-live="polite" /> : null}
      {error ? <p className="assistant-error" role="alert">{error.message}</p> : null}
      {data && !data.available ? <div className="backend-notice" role="status"><CircleAlert aria-hidden="true" /><span>{data.notes?.join(" ") || "Stock recommendations are unavailable for this dataset."}</span></div> : null}

      {data?.available && rows.length ? (
        <>
          <section className="metric-grid analytics-summary" aria-label="Stock recommendation metrics">
            <Card className="metric-card"><CardContent className="metric-content"><div className="metric-topline"><span className="metric-label">Products analysed</span><span className="metric-icon"><PackageSearch aria-hidden="true" /></span></div><div className="metric-value"><AnimatedNumber value={rows.length} format={(value) => formatNumber(value, 0)} /></div><div className="metric-footnote">From the mapped product field</div></CardContent></Card>
            <Card className="metric-card"><CardContent className="metric-content"><div className="metric-topline"><span className="metric-label">Products needing action</span><span className="metric-icon"><CircleAlert aria-hidden="true" /></span></div><div className="metric-value"><AnimatedNumber value={needsReorder} format={(value) => formatNumber(value, 0)} /></div><div className="metric-footnote">Out of stock, critical, or low{overstocked ? ` · ${overstocked} overstocked` : ""}</div></CardContent></Card>
            <Card className="metric-card"><CardContent className="metric-content"><div className="metric-topline"><span className="metric-label">Suggested reorder units</span><span className="metric-icon"><Activity aria-hidden="true" /></span></div><div className="metric-value"><AnimatedNumber value={data.stock_available ? totalSuggested : null} format={(value) => formatNumber(value, 0)} /></div><div className="metric-footnote">{data.stock_available ? "Requires a current-stock column" : "Add a current-stock column to unlock"}</div></CardContent></Card>
            <Card className="metric-card"><CardContent className="metric-content"><div className="metric-topline"><span className="metric-label">Stock state</span><span className="metric-icon"><Database aria-hidden="true" /></span></div><div className="metric-value stock-state-value">{data.stock_available ? (reorderRow("reorder") ? "Reorder" : "Healthy") : "No stock data"}</div><div className="metric-footnote">{data.stock_available ? "Derived from observed stock levels" : "Demand planning only"}</div></CardContent></Card>
          </section>

          {!data.stock_available ? (
            <div className="backend-notice" role="status"><CircleAlert aria-hidden="true" /><span>{data.notes?.join(" ") || "No current-stock column was found. Demand, safety stock, and reorder points are calculated, but days remaining, depletion dates, and suggested quantities need a stock level."}</span></div>
          ) : null}

          {chartRows.length ? (
            <Card className="panel-card">
              <CardHeader className="panel-header"><div><CardTitle className="panel-title">Top replenishment needs</CardTitle><p className="panel-subtitle">Top {chartRows.length} products by {chartMetric === "suggested_reorder_quantity" ? "suggested reorder quantity" : "reorder point"}</p></div><Badge variant="secondary">Live dataset</Badge></CardHeader>
              <CardContent>
                <div className="analytics-chart">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart key={isAnimationActive ? "animated" : "static"} data={chartRows} layout="vertical" margin={{ top: 4, right: 16, left: 4, bottom: 4 }}>
                      <CartesianGrid stroke="#edf0f5" strokeDasharray="3 4" horizontal={false} />
                      <XAxis type="number" tickLine={false} axisLine={false} tick={{ fill: "#8993a2", fontSize: 9 }} tickFormatter={(value: number) => new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 }).format(value)} />
                      <YAxis type="category" dataKey="label" width={126} tickLine={false} axisLine={false} tick={{ fill: "#8993a2", fontSize: 8 }} />
                      <Tooltip formatter={(value) => [formatNumber(Number(value), 2), chartMetric === "suggested_reorder_quantity" ? "Suggested reorder" : "Reorder point"]} />
                      <Bar dataKey="value" name="Units" radius={[0, 6, 6, 0]} barSize={14} isAnimationActive={isAnimationActive} animationDuration={animationDuration} animationEasing={animationEasing}>
                        {chartRows.map((row, index) => <Cell key={`${row.label}-${index}`} fill={index % 2 === 0 ? "#3e75bd" : "#a6c4f1"} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          ) : null}

          <Card className="panel-card">
            <CardHeader className="panel-header">
              <div><CardTitle className="panel-title">Replenishment recommendations</CardTitle><p className="panel-subtitle">{filteredRows.length} of {rows.length} products shown · demand, safety stock, reorder point, and status are calculated by the existing inventory module</p></div>
              <Button type="button" variant="outline" size="sm" disabled={!filteredRows.length} onClick={() => downloadRowsAsCsv("stock-recommendations.csv", filteredRows)}>Download CSV</Button>
            </CardHeader>
            <CardContent>
              <div className="stock-toolbar">
                <label className="compact-field"><span>Search product</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Filter products…" /></label>
                <label className="compact-field"><span>Status</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="all">All statuses</option>{statuses.map((status) => <option key={status} value={status}>{status}</option>)}</select></label>
                <label className="compact-field"><span>Sort by</span><select value={sortKey} onChange={(event) => setSortKey(event.target.value)}>{STOCK_COLUMNS.filter((column) => column.kind === "number" || column.key === "product").map((column) => <option key={column.key} value={column.key}>{column.label}</option>)}</select></label>
                <Button type="button" variant="outline" size="sm" onClick={() => toggleSort(sortKey)}>{sortDescending ? "Descending ↓" : "Ascending ↑"}</Button>
              </div>
              <div className="table-wrap">
                <Table>
                  <TableHeader><TableRow>{STOCK_COLUMNS.map((column) => <TableHead key={column.key}>{column.label}</TableHead>)}</TableRow></TableHeader>
                  <TableBody>
                    {filteredRows.slice(0, 250).map((row, index) => (
                      <TableRow key={`${String(row.product)}-${index}`}>
                        {STOCK_COLUMNS.map((column) => (
                          <TableCell key={column.key} className={column.key === "status" ? "stock-status-cell" : undefined}>{stockCellValue(row[column.key], column.kind)}</TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              {!filteredRows.length ? <p className="empty-copy">No products match the current search and status filters.</p> : null}
              {data.assumptions?.length ? <div className="inventory-assumptions">{data.assumptions.map((assumption) => <p key={assumption}>{assumption}</p>)}</div> : null}
              {data.notes?.length ? <p className="dashboard-footnote">{data.notes.join(" ")}</p> : null}
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}


function highlightInline(text: string, keyPrefix: string): ReactNode[] {
  return text.split(/(₹\s?[\d,]+(?:\.\d+)?|\b\d[\d,]*(?:\.\d+)?\s?%|\b\d{1,3}(?:,\d{2,3})+(?:\.\d+)?\b)/g).map((part, index) =>
    /^(₹|\d)/.test(part) && /[\d%]/.test(part)
      ? <span className="answer-figure" key={`${keyPrefix}-figure-${index}`}>{part}</span>
      : <span key={`${keyPrefix}-text-${index}`}>{part}</span>,
  );
}

function highlightFigures(text: string): ReactNode[] {
  // Support inline **emphasis** from the verified answer composer without
  // rendering raw Markdown markers to the user.
  return text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map((part, index) =>
    part.startsWith("**") && part.endsWith("**")
      ? <strong key={`bold-${index}`}>{part.slice(2, -2)}</strong>
      : <span key={`inline-${index}`}>{highlightInline(part, `inline-${index}`)}</span>,
  );
}

/** Lightweight, safe renderer for the assistant's plain-text answers. */
function StructuredAnswer({ text }: { text: string }) {
  const lines = text.replaceAll("\r\n", "\n").split("\n");
  const blocks: ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  let table: string[][] = [];

  function flush() {
    if (list) {
      const Tag = list.ordered ? "ol" : "ul";
      blocks.push(<Tag key={`list-${blocks.length}`}>{list.items.map((item, index) => <li key={index}>{highlightFigures(item)}</li>)}</Tag>);
      list = null;
    }
    if (table.length) {
      const [header, ...rows] = table.filter((row) => !row.every((cell) => /^:?-{2,}:?$/.test(cell.trim())));
      blocks.push(
        <div className="table-wrap" key={`table-${blocks.length}`}>
          <table>
            <thead><tr>{header.map((cell, index) => <th key={index}>{cell.trim()}</th>)}</tr></thead>
            <tbody>{rows.map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={cellIndex}>{highlightFigures(cell.trim())}</td>)}</tr>)}</tbody>
          </table>
        </div>,
      );
      table = [];
    }
  }

  for (const raw of lines) {
    const line = raw.trimEnd();
    const trimmed = line.trim();
    if (!trimmed) { flush(); continue; }
    if (/^\|.*\|$/.test(trimmed)) {
      if (list) flush();
      table.push(trimmed.slice(1, -1).split("|"));
      continue;
    }
    if (table.length) flush();
    const heading = trimmed.match(/^#{1,6}\s+(.+)$/);
    const boldHeading = trimmed.match(/^\*\*(.+?)\*\*:?$/);
    if (heading || boldHeading) {
      flush();
      blocks.push(<h4 key={`heading-${blocks.length}`}>{heading ? heading[1] : boldHeading![1]}</h4>);
      continue;
    }
    const bullet = trimmed.match(/^[-*•]\s+(.+)$/);
    const numbered = trimmed.match(/^\d+[.)]\s+(.+)$/);
    if (bullet || numbered) {
      const ordered = Boolean(numbered);
      if (table.length) flush();
      if (!list || list.ordered !== ordered) {
        flush();
        list = { ordered, items: [] };
      }
      (list as { ordered: boolean; items: string[] }).items.push((bullet ?? numbered)![1]);
      continue;
    }
    flush();
    blocks.push(<p key={`paragraph-${blocks.length}`}>{highlightFigures(trimmed)}</p>);
  }
  flush();
  return <div className="assistant-answer-body">{blocks}</div>;
}

function AssistantWorkspace({ item }: { item: NavigationItem }) {
  const { dataset } = useDataset();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<{ text: string; verified: boolean; sources: string[] } | null>(null);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState("");

  async function submitQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!dataset || !question.trim() || asking) return;
    setAsking(true);
    setError("");
    try {
      const response = await fetch("/api/retailmind/ai/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ dataset_id: dataset.id, question: question.trim() }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "The assistant could not answer this question.");
      setAnswer(result);
      setQuestion("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The assistant could not answer this question.");
    } finally {
      setAsking(false);
    }
  }

  return (
    <div className="page-stack">
      <PageHeading item={item} />
      <div className="assistant-layout">
        <Card className="panel-card assistant-card"><CardContent>
          <div className="assistant-welcome"><span className="assistant-avatar"><Bot aria-hidden="true" /></span><Badge variant="outline">Verified answers</Badge><h2>Your business, in context</h2><p>Ask about sales, profit, products, or customers. Answers use the existing Pandas-backed assistant.</p></div>
          <div className="suggestion-list" aria-label="Example questions">{["What is the total sales?", "Which product has the highest revenue?", "Show sales by month"].map((prompt) => <button className="suggestion-chip" key={prompt} type="button" disabled={!dataset || asking} title={!dataset ? "Upload a dataset first" : undefined} onClick={() => setQuestion(prompt)}>{prompt}<ArrowRight aria-hidden="true" /></button>)}</div>
          <form onSubmit={submitQuestion}>
            <label className="assistant-composer-label" htmlFor="assistant-question">Your question</label>
            <div className="assistant-composer"><textarea id="assistant-question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder={dataset ? "Ask about the active dataset…" : "Upload a dataset to start asking questions"} disabled={!dataset || asking} rows={4} maxLength={2000} /><Button type="submit" disabled={!dataset || !question.trim() || asking}>{asking ? "Thinking…" : "Ask"}</Button></div>
          </form>
          {error ? <p className="assistant-error" role="alert">{error}</p> : null}
          {asking ? <div className="assistant-answer assistant-answer-loading" role="status" aria-live="polite"><span className="assistant-typing" aria-hidden="true"><i /><i /><i /></span><p>Analysing the active dataset…</p></div> : null}
          {answer ? <div className="assistant-answer" role="status"><div><strong>Verified answer</strong>{answer.verified ? <Badge variant="secondary">Data-backed</Badge> : null}</div><StructuredAnswer text={answer.text} />{answer.sources.length ? <div className="assistant-sources"><h4>Evidence</h4><ul>{answer.sources.map((source) => <li key={source}>{source}</li>)}</ul></div> : null}</div> : null}
          {!answer && !asking && dataset ? <p className="assistant-note">Ask a question above. Answers are computed from your active dataset and are never generated from placeholder values.</p> : null}
          {!dataset ? <p className="assistant-note"><LockKeyhole aria-hidden="true" /> Upload a dataset before sending questions.</p> : null}
        </CardContent></Card>
        <Card className="panel-card evidence-card"><CardHeader><CardTitle className="panel-title">Answer sources</CardTitle><p className="panel-subtitle">Evidence for generated responses.</p></CardHeader><CardContent><EmptyState icon={Search} title="Source records are available" description="Answers are computed from your active dataset. Document citations are part of the separate RAG workspace." action="Open RAG assistant" href="/rag-assistant" /></CardContent></Card>
      </div>
    </div>
  );
}

type RAGDocument = { name: string; characters: number; chunks: number; pages?: number | null; embedding?: string; doc_id?: string; status?: string };
type RAGSource = { doc_name: string; chunk_index: number; score: number; excerpt: string; page?: number | null; chunk_id?: string; citation?: string };
type RAGResponse = { text: string; verified_retrieval: boolean; sources: RAGSource[]; note: string; used_llm: boolean; generation?: { available: boolean; provider: string; model: string | null; message: string } };
type RAGTurn = { question: string; answer: RAGResponse };

function RagAssistantPage({ item }: { item: NavigationItem }) {
  const { data, error: loadError, isLoading, mutate } = useSWR<{ documents: RAGDocument[]; storage: string }>("/api/retailmind/ai/rag/documents", fetchJson);
  const [file, setFile] = useState<File | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<RAGResponse | null>(null);
  const [uploading, setUploading] = useState(false);
  const [asking, setAsking] = useState(false);
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");
  const [turns, setTurns] = useState<RAGTurn[]>([]);
  const [reindexing, setReindexing] = useState("");

  async function uploadDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || uploading) return;
    setUploading(true);
    setActionError("");
    setNotice("");
    const formData = new FormData();
    formData.append("file", file);
    try {
      const response = await fetch("/api/retailmind/ai/rag/documents", { method: "POST", body: formData });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "The document could not be indexed.");
      setFile(null);
      setNotice(`${payload.document.name} is indexed with ${payload.chunk_count} source chunks.`);
      await mutate();
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : "The document could not be indexed.");
    } finally {
      setUploading(false);
    }
  }

  async function reindexDocument(name: string) {
    setActionError("");
    setNotice("");
    setReindexing(name);
    try {
      const response = await fetch(`/api/retailmind/ai/rag/documents/${encodeURIComponent(name)}/reindex`, { method: "POST" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "The document could not be re-indexed.");
      await mutate();
      setNotice(`${name} was re-indexed with ${payload.chunks} chunks using ${payload.embedding} embeddings.`);
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : "The document could not be re-indexed.");
    } finally {
      setReindexing("");
    }
  }

  async function removeDocument(name: string) {
    setActionError("");
    setNotice("");
    try {
      const response = await fetch(`/api/retailmind/ai/rag/documents/${encodeURIComponent(name)}`, { method: "DELETE" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "The document could not be removed.");
      await mutate();
      setNotice(`${name} was removed from this session index.`);
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : "The document could not be removed.");
    }
  }

  async function askQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!question.trim() || asking || !data?.documents.length) return;
    setAsking(true);
    setActionError("");
    setNotice("");
    try {
      const response = await fetch("/api/retailmind/ai/rag", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          question: question.trim(),
          history: turns.flatMap((turn) => [
            { role: "user", content: turn.question },
            { role: "assistant", content: turn.answer.text },
          ]),
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "The retrieval assistant could not answer.");
      const responsePayload = payload as RAGResponse;
      setAnswer(responsePayload);
      setTurns((current) => [...current, { question: question.trim(), answer: responsePayload }]);
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : "The retrieval assistant could not answer.");
    } finally {
      setAsking(false);
    }
  }

  return (
    <div className="page-stack">
      <PageHeading item={item} />
      <div className="rag-layout">
        <Card className="panel-card rag-chat-card">
          <CardHeader><CardTitle className="panel-title">Ask your documents</CardTitle><p className="panel-subtitle">Answers use retrieved text and cite the source document and chunk.</p></CardHeader>
          <CardContent>
            <form className="rag-question-form" onSubmit={askQuestion}>
              <label htmlFor="rag-question">Your question</label>
              <textarea id="rag-question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask a question supported by your uploaded documents…" rows={3} maxLength={2000} disabled={!data?.documents.length || asking} />
              <div className="rag-question-footer"><span>{data?.documents.length ? `${data.documents.length} indexed document${data.documents.length === 1 ? "" : "s"}` : "Upload a document to begin"}</span><Button type="submit" disabled={!question.trim() || !data?.documents.length || asking}>{asking ? "Retrieving…" : "Ask documents"}</Button></div>
            </form>
            {loadError ? <p className="assistant-error" role="alert">{loadError.message}</p> : null}
            {actionError ? <p className="assistant-error" role="alert">{actionError}</p> : null}
            {notice ? <p className="upload-message" role="status">{notice}</p> : null}
            {isLoading ? <div className="loading-panel" aria-label="Loading document index" /> : null}
            {asking ? <div className="rag-answer" role="status" aria-live="polite"><p>Searching the indexed documents and preparing a grounded answer…</p></div> : null}
            {answer ? <div className="rag-answer" role="status"><div className="rag-answer-heading"><strong>Answer</strong><Badge variant="secondary">{answer.sources.length ? "Source-backed" : "No supporting evidence"}</Badge><Badge variant="outline">{answer.used_llm ? "LLM grounded in sources" : "Extractive · no LLM configured"}</Badge></div><StructuredAnswer text={answer.text} /><small>{answer.note}</small>{answer.generation ? <small>{answer.generation.message}</small> : null}{answer.sources.length ? <div className="rag-sources"><h3>Sources</h3>{answer.sources.map((source) => <article key={source.chunk_id ?? `${source.doc_name}-${source.chunk_index}`}><strong>{source.doc_name}{source.page ? ` · page ${source.page}` : ""} · chunk {source.chunk_index + 1}</strong><span>Relevance {source.score.toFixed(2)}</span><p>{source.excerpt}</p></article>)}</div> : null}</div> : null}
            {turns.length > 1 ? <div className="rag-conversation" aria-label="Conversation history"><h3 className="rag-conversation-title">Conversation</h3>{turns.slice(0, -1).map((turn, index) => <div className="rag-turn" key={index}><strong>You asked</strong><p>{turn.question}</p><strong>Answer</strong><p>{turn.answer.text.slice(0, 600)}{turn.answer.text.length > 600 ? "…" : ""}</p></div>)}</div> : null}
          </CardContent>
        </Card>
        <Card className="panel-card rag-documents-card">
          <CardHeader><CardTitle className="panel-title">Knowledge sources</CardTitle><p className="panel-subtitle">Up to 25 documents, 5 MB each.</p></CardHeader>
          <CardContent>
            <form className="rag-upload-form" onSubmit={uploadDocument}>
              <label htmlFor="rag-file">Add a document</label>
              <input id="rag-file" type="file" accept=".txt,.md,.csv,.json,.pdf,.docx,.xlsx,.xls,.xlsm" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
              <Button type="submit" variant="outline" size="sm" disabled={!file || uploading}>{uploading ? "Indexing…" : "Index document"}</Button>
            </form>
            <div className="rag-document-list" aria-live="polite">
              {data?.documents.length ? data.documents.map((document) => <div className="rag-document-row" key={document.name}><span className="file-type-icon"><FileText aria-hidden="true" /></span><div><strong>{document.name}</strong><span>{document.chunks} chunks · {document.characters.toLocaleString()} characters{document.pages ? ` · ${document.pages} pages` : ""} · {document.embedding ?? "local"} embeddings{document.status ? ` · ${document.status}` : ""}</span></div><div className="rag-document-actions"><Button variant="ghost" size="sm" disabled={reindexing === document.name} aria-label={`Re-index ${document.name}`} onClick={() => reindexDocument(document.name)}>{reindexing === document.name ? "Re-indexing…" : "Re-index"}</Button><Button variant="ghost" size="sm" aria-label={`Remove ${document.name}`} onClick={() => removeDocument(document.name)}>Remove</Button></div></div>) : !isLoading ? <EmptyState icon={FileText} title="No documents indexed" description="Add a text, spreadsheet, JSON, PDF, DOCX, or Excel file to create a private retrieval index." /> : null}
            </div>
            <p className="rag-storage-note"><ShieldCheck aria-hidden="true" /> The index and document metadata are persisted per account and reloaded automatically after the Python service restarts. Documents are visible only to the signed-in owner.</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function IntelligencePage({ item }: { item: NavigationItem }) {
  const { dataset } = useDataset();
  const isRag = item.href === "/rag-assistant";
  const isSegmentation = item.href === "/customer-segmentation" || item.href === "/customer-tagging";
  const isCustomerTagging = item.href === "/customer-tagging";
  const [customerPage, setCustomerPage] = useState({ datasetId: "", offset: 0 });
  const [clusterChoice, setClusterChoice] = useState<"auto" | number>("auto");
  const [tagSearch, setTagSearch] = useState("");
  const [tagFilter, setTagFilter] = useState("all");
  const [clusterFilter, setClusterFilter] = useState("all");
  const [tagSort, setTagSort] = useState<"monetary" | "recency" | "frequency" | "customer">("monetary");
  const customerOffset = customerPage.datasetId === dataset?.id ? customerPage.offset : 0;
  function setCustomerOffset(nextOffset: number | ((currentOffset: number) => number)) {
    const currentOffset = customerPage.datasetId === dataset?.id ? customerPage.offset : 0;
    setCustomerPage({
      datasetId: dataset?.id ?? "",
      offset: typeof nextOffset === "function" ? nextOffset(currentOffset) : nextOffset,
    });
  }
  const segmentationParams = new URLSearchParams();
  if (isCustomerTagging) {
    segmentationParams.set("offset", String(customerOffset));
    segmentationParams.set("limit", "100");
    segmentationParams.set("sort", tagSort);
    if (tagFilter !== "all") segmentationParams.set("tag", tagFilter);
    if (clusterFilter !== "all") segmentationParams.set("cluster", clusterFilter);
    if (tagSearch.trim()) segmentationParams.set("search", tagSearch.trim());
  } else if (isSegmentation && clusterChoice !== "auto") {
    segmentationParams.set("clusters", String(clusterChoice));
  }
  const segmentationQuery = isSegmentation && segmentationParams.toString() ? `?${segmentationParams.toString()}` : "";
  const endpoint = !dataset || item.href === "/assistant" || isRag ? null
    : isSegmentation ? `/api/retailmind/segmentation/${encodeURIComponent(dataset.id)}${segmentationQuery}`
      : item.href === "/smart-alerts" ? `/api/retailmind/ai/alerts/${encodeURIComponent(dataset.id)}`
        : `/api/retailmind/ai/insights/${encodeURIComponent(dataset.id)}`;
  const { data, error, isLoading, mutate } = useSWR<IntelligenceResult>(endpoint, fetchJson);
  const [alertSeverity, setAlertSeverity] = useState("all");
  const [alertStatus, setAlertStatus] = useState("all");
  const [alertActionError, setAlertActionError] = useState("");
  const [alertActionPending, setAlertActionPending] = useState("");
  const [prefSaving, setPrefSaving] = useState(false);
  const [emailTestPending, setEmailTestPending] = useState(false);
  const [emailTestResult, setEmailTestResult] = useState("");
  const { data: alertPreferences, mutate: mutateAlertPreferences } = useSWR<AlertPreferences>(
    item.href === "/smart-alerts" ? "/api/retailmind/ai/alerts/preferences" : null,
    fetchJson,
  );

  async function saveAlertPreferences(enabled: boolean, minSeverity: "critical" | "warning" | "info", frequency: "instant" | "daily") {
    if (prefSaving) return;
    setPrefSaving(true);
    setAlertActionError("");
    try {
      const response = await fetch("/api/retailmind/ai/alerts/preferences", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ enabled, min_severity: minSeverity, frequency }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Notification preferences could not be saved.");
      await mutateAlertPreferences();
    } catch (reason) {
      setAlertActionError(reason instanceof Error ? reason.message : "Notification preferences could not be saved.");
    } finally {
      setPrefSaving(false);
    }
  }

  async function sendTestEmail() {
    if (emailTestPending) return;
    setEmailTestPending(true);
    setEmailTestResult("");
    setAlertActionError("");
    try {
      const response = await fetch("/api/retailmind/ai/alerts/email/test", { method: "POST" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "The test email could not be requested.");
      setEmailTestResult(
        payload.status === "accepted_by_smtp"
          ? "Test email accepted by SMTP. Check the signed-in account inbox."
          : `Test email not sent: ${String(payload.status).replaceAll("_", " ")}${payload.missing?.length ? ` (missing ${payload.missing.join(", ")})` : ""}.`,
      );
    } catch (reason) {
      setAlertActionError(reason instanceof Error ? reason.message : "The test email could not be requested.");
    } finally {
      setEmailTestPending(false);
    }
  }

  async function updateAlert(alertId: string, action: "acknowledge" | "dismiss" | "resolve" | "reopen") {
    if (!dataset || alertActionPending) return;
    setAlertActionError("");
    setAlertActionPending(alertId);
    try {
      const response = await fetch(`/api/retailmind/ai/alerts/${encodeURIComponent(dataset.id)}/${encodeURIComponent(alertId)}/status`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "The alert status could not be saved.");
      await mutate();
    } catch (reason) {
      setAlertActionError(reason instanceof Error ? reason.message : "The alert status could not be saved.");
    } finally {
      setAlertActionPending("");
    }
  }
  const filteredAlerts = (data?.alerts ?? []).filter((alert) =>
    (alertSeverity === "all" || alert.severity === alertSeverity)
    && (alertStatus === "all" || alert.status === alertStatus)
  );

  if (item.href === "/assistant") return <AssistantWorkspace item={item} />;
  if (isRag) return <RagAssistantPage item={item} />;

  const list = isSegmentation ? (isCustomerTagging ? data?.customers ?? [] : data?.summary ?? []) : [];
  const fields = list.length ? Object.keys(list[0]) : [];
  const customerTotal = data?.customer_total ?? list.length;
  const topSegment = isSegmentation && !isCustomerTagging ? String(list[0]?.segment ?? "—") : "";
  const churnRiskCustomers = isSegmentation && !isCustomerTagging
    ? list.reduce((sum, row) => sum + (typeof row.rule_based_risk_customers === "number" ? row.rule_based_risk_customers : 0), 0)
    : 0;
  const silhouette = typeof data?.silhouette === "number" ? data.silhouette : null;
  const hasPreviousCustomerPage = customerOffset > 0;
  const hasNextCustomerPage = customerOffset + list.length < customerTotal;

  function formatSummaryCell(field: string, value: string | number | boolean | null) {
    if (value == null) return "—";
    if (["revenue", "avg_monetary_value", "avg_purchase_value"].includes(field)) return formatCurrencyPrecise(Number(value));
    if (["customer_share", "revenue_share"].includes(field)) return formatPercent(Number(value) * 100);
    if (["avg_frequency", "avg_recency_days"].includes(field)) return formatNumber(Number(value), field === "avg_frequency" ? 2 : 0);
    if (typeof value === "number") return formatNumber(value, 2);
    return String(value);
  }
  return (
    <div className="page-stack">
      <PageHeading item={item} />
      {isSegmentation && !isCustomerTagging ? (
        <div className="segmentation-toolbar" aria-label="Segmentation configuration">
          <label className="compact-field">
            <span>Number of segments</span>
            <select
              value={clusterChoice}
              onChange={(event) => setClusterChoice(event.target.value === "auto" ? "auto" : Number(event.target.value))}
              disabled={!dataset}
            >
              <option value="auto">Auto (best silhouette)</option>
              {[2, 3, 4, 5, 6, 7, 8].map((count) => <option key={count} value={count}>{count} segments</option>)}
            </select>
          </label>
          <span className="filter-note">
            {data?.cluster_count ? `K-Means k=${data.cluster_count}` : "Choose a dataset to calculate segments"}
            {typeof data?.silhouette === "number" ? ` · silhouette ${data.silhouette.toFixed(3)}` : ""}
          </span>
        </div>
      ) : null}
      {data?.available && isSegmentation && !isCustomerTagging && list.length ? (
        <section className="metric-grid" aria-label="Segmentation metrics">
          <div className="metric-card"><div className="metric-content"><span className="metric-label">Total customers</span><span className="metric-value">{customerTotal.toLocaleString("en-IN")}</span><span className="metric-footnote">Distinct customer identifiers</span></div></div>
          <div className="metric-card"><div className="metric-content"><span className="metric-label">Total segments</span><span className="metric-value">{data?.cluster_count ?? "—"}</span><span className="metric-footnote">{silhouette != null ? `Silhouette ${silhouette.toFixed(3)}` : "Cluster separation unavailable"}</span></div></div>
          <div className="metric-card"><div className="metric-content"><span className="metric-label">VIP customers</span><span className="metric-value">{(data?.tags?.VIP ?? 0).toLocaleString("en-IN")}</span><span className="metric-footnote">High value, frequent, recent</span></div></div>
          <div className="metric-card"><div className="metric-content"><span className="metric-label">Rule-based churn risk</span><span className="metric-value">{churnRiskCustomers.toLocaleString("en-IN")}</span><span className="metric-footnote">Transparent recency/frequency rule</span></div></div>
          <div className="metric-card"><div className="metric-content"><span className="metric-label">Top segment by revenue</span><span className="metric-value segmentation-metric-text">{topSegment}</span><span className="metric-footnote">Highest revenue share</span></div></div>
        </section>
      ) : null}
      {isSegmentation && !isCustomerTagging && data?.summary?.length ? (
        <Card className="panel-card">
          <CardHeader><CardTitle className="panel-title">Segment distribution and revenue share</CardTitle><p className="panel-subtitle">Each bar is calculated from the full customer result; percentages reflect the active dataset.</p></CardHeader>
          <CardContent><div className="segment-mix">
            {data.summary.map((row) => {
              const segment = String(row.segment ?? "Segment");
              const customerShare = Number(row.customer_share ?? 0) * 100;
              const revenueShare = Number(row.revenue_share ?? 0) * 100;
              return <article className="segment-mix-row" key={segment}>
                <div className="segment-mix-head"><strong>{segment}</strong><span>{formatNumber(Number(row.customers ?? 0), 0)} customers · {formatPercent(revenueShare)} of revenue</span></div>
                <div className="segment-bar" role="img" aria-label={`${segment}: ${formatPercent(customerShare)} of customers and ${formatPercent(revenueShare)} of revenue`}>
                  <span className="segment-bar-customers" style={{ width: `${Math.max(1, Math.min(100, customerShare))}%` }} />
                  <span className="segment-bar-revenue" style={{ width: `${Math.max(1, Math.min(100, revenueShare))}%` }} />
                </div>
                <p>{SEGMENT_GUIDANCE[segment] ?? "Compare this group's revenue and recency before choosing a retention action."}</p>
              </article>;
            })}
          </div><div className="segment-legend"><span><i className="segment-key-customers" /> Customer share</span><span><i className="segment-key-revenue" /> Revenue share</span></div></CardContent>
        </Card>
      ) : null}
      {isCustomerTagging && data?.available && data.tags ? (
        <section className="metric-grid" aria-label="Customer tag metrics">
          <div className="metric-card"><div className="metric-content"><span className="metric-label">Total customers</span><span className="metric-value">{(data.tag_total ?? customerTotal).toLocaleString("en-IN")}</span><span className="metric-footnote">Distinct customers with valid RFM</span></div></div>
          <div className="metric-card"><div className="metric-content"><span className="metric-label">VIP customers</span><span className="metric-value">{(data.tags.VIP ?? 0).toLocaleString("en-IN")}</span><span className="metric-footnote">High value, frequent, recent</span></div></div>
          <div className="metric-card"><div className="metric-content"><span className="metric-label">Loyal customers</span><span className="metric-value">{(data.tags.Loyal ?? 0).toLocaleString("en-IN")}</span><span className="metric-footnote">Repeat purchase behaviour</span></div></div>
          <div className="metric-card"><div className="metric-content"><span className="metric-label">At-risk customers</span><span className="metric-value">{(data.tags["At Risk"] ?? 0).toLocaleString("en-IN")}</span><span className="metric-footnote">High value but inactive</span></div></div>
          <div className="metric-card"><div className="metric-content"><span className="metric-label">New customers</span><span className="metric-value">{(data.tags.New ?? 0).toLocaleString("en-IN")}</span><span className="metric-footnote">Recent first purchase</span></div></div>
        </section>
      ) : null}
      {isCustomerTagging && data?.tags ? (
        <Card className="panel-card compact-panel">
          <CardHeader><CardTitle className="panel-title">Tag distribution</CardTitle><p className="panel-subtitle">Behaviour-based tags calculated from the full RFM result.</p></CardHeader>
          <CardContent><div className="segment-mix">
            {Object.entries(data.tags).sort(([, left], [, right]) => right - left).map(([tag, count]) => {
              const total = data.tag_total || Object.values(data.tags ?? {}).reduce((sum, value) => sum + value, 0);
              const share = total ? (count / total) * 100 : 0;
              return <article className="tag-mix-row" key={tag}><TagBadge tag={tag} /><div className="segment-bar"><span className={`segment-bar-tag ${TAG_CLASSES[tag] ?? "tag-regular"}`} style={{ width: `${Math.max(2, share)}%` }} /></div><span className="tag-mix-count">{count.toLocaleString("en-IN")} · {formatPercent(share)}</span></article>;
            })}
          </div></CardContent>
        </Card>
      ) : null}
      {item.href === "/smart-alerts" && data?.alerts ? <div className="alert-filter-toolbar" aria-label="Filter smart alerts"><label className="compact-field"><span>Severity</span><select value={alertSeverity} onChange={(event) => setAlertSeverity(event.target.value)}><option value="all">All severities</option><option value="critical">Critical</option><option value="warning">Warning</option><option value="info">Info</option></select></label><label className="compact-field"><span>Status</span><select value={alertStatus} onChange={(event) => setAlertStatus(event.target.value)}><option value="all">All statuses</option><option value="new">New</option><option value="acknowledged">Acknowledged</option><option value="resolved">Resolved</option><option value="dismissed">Dismissed</option></select></label><Button type="button" variant="outline" size="sm" disabled={!filteredAlerts.length} onClick={() => downloadRowsAsCsv("smart-alerts.csv", filteredAlerts.map(({ evidence, ...alert }) => ({ ...alert, evidence: evidence ? JSON.stringify(evidence) : "" })))}>Export filtered CSV</Button></div> : null}
      {item.href === "/smart-alerts" && data?.email ? (
        <div className="alert-email-status" role="status">
          <strong>Email notifications</strong>
          <label className="alert-pref-toggle"><input type="checkbox" checked={alertPreferences?.enabled ?? false} disabled={prefSaving} onChange={(event) => saveAlertPreferences(event.target.checked, alertPreferences?.min_severity ?? "warning", alertPreferences?.frequency ?? "instant")} /> Email new alerts</label>
          <label className="alert-pref-toggle">Minimum severity <select value={alertPreferences?.min_severity ?? "warning"} disabled={prefSaving} onChange={(event) => saveAlertPreferences(alertPreferences?.enabled ?? false, event.target.value as "critical" | "warning" | "info", alertPreferences?.frequency ?? "instant")}><option value="critical">Critical</option><option value="warning">High</option><option value="info">Medium</option></select></label>
          <label className="alert-pref-toggle">Frequency <select value={alertPreferences?.frequency ?? "instant"} disabled={prefSaving} onChange={(event) => saveAlertPreferences(alertPreferences?.enabled ?? false, alertPreferences?.min_severity ?? "warning", event.target.value as "instant" | "daily")}><option value="instant">Each alert</option><option value="daily">Daily digest</option></select></label>
          <span>{alertPreferences?.configured ? `SMTP ready · ${alertPreferences.recipient_count} recipient(s) · ${alertPreferences.frequency === "daily" ? "daily digest on the first check each day" : "one email per alert"} · up to 3 attempts.` : alertPreferences?.smtp_ready ? "SMTP is ready but email notifications are switched off for this account." : "SMTP is not configured on the server, so enabling this will not deliver mail."}</span>
          {alertPreferences?.missing?.length ? <span>Missing: {alertPreferences.missing.join(", ")}</span> : null}
          <Button type="button" variant="outline" size="sm" disabled={emailTestPending || !alertPreferences?.smtp_ready} onClick={sendTestEmail}>{emailTestPending ? "Sending test…" : "Send test email"}</Button>
          {emailTestResult ? <span role="status">{emailTestResult}</span> : null}
          {data.email.sent?.length ? <span>{data.email.sent.length} new alert email(s) accepted by SMTP.</span> : null}
          {data.email.failed?.length ? <span>{data.email.failed.length} email attempt(s) failed and will retry on the next check (max 3).</span> : null}
        </div>
      ) : null}
      {alertActionError ? <p className="assistant-error" role="alert">{alertActionError}</p> : null}
      {!dataset ? <EmptyState icon={Database} title="Choose a dataset to begin" description="Upload a CSV or Excel file to calculate this view from your data." action="Upload a dataset" /> : null}
      {isLoading ? <div className="loading-panel" aria-live="polite" /> : null}
      {error ? <p className="assistant-error" role="alert">{error.message}</p> : null}
      {data && !data.available ? <div className="backend-notice" role="status"><CircleAlert aria-hidden="true" /><span>{data.notes?.join(" ") || "This feature is unavailable for the uploaded dataset."}</span></div> : null}
      {data?.insights?.length ? <section className="insight-card-grid" aria-label="Business insights">{data.insights.map((insight, index) => <article className="insight-tile" key={insight}><span className="insight-tile-index">{String(index + 1).padStart(2, "0")}</span><div><h3>{/risk|declin|below-median|drop|loss|negative|underperform/i.test(insight) ? "Risk" : /\bopportunit|\bincrease|\bgrow|\bbest\b|\btop\b/i.test(insight) ? "Opportunity" : "Observation"}</h3><p>{insight}</p></div></article>)}</section> : null}
      {item.href === "/smart-alerts" && filteredAlerts.length ? <div className="info-grid alert-card-grid">{filteredAlerts.map((alert, index) => <Card className="panel-card" id={alert.id ? `alert-${alert.id}` : undefined} key={alert.id ?? `${alert.metric}-${index}`}><CardHeader><div className="alert-card-heading"><CardTitle className="panel-title">{alert.title}</CardTitle><div className="alert-badges"><Badge variant={alert.severity === "critical" ? "destructive" : "outline"}>{alert.severity_label ?? alert.severity}</Badge><Badge variant="secondary">{alert.status ?? "new"}</Badge></div></div><p className="panel-subtitle">{alert.description}</p></CardHeader><CardContent><p className="empty-copy">{alert.suggestion}</p><div className="alert-evidence"><span>{alert.scope_label ?? alert.scope ?? "Overall"}{alert.scope_dimension ? ` · ${alert.scope_dimension}` : ""}</span><span>{alert.comparison_period || "Comparison period unavailable"}</span></div>{alert.current_value != null || alert.previous_value != null ? <p className="alert-values">Current {alert.current_value?.toLocaleString("en-IN") ?? "—"} · Previous {alert.previous_value?.toLocaleString("en-IN") ?? "—"}{alert.pct_change != null ? ` · ${(alert.pct_change * 100).toFixed(1)}%` : ""}</p> : null}{alert.acknowledged_at ? <p className="alert-values">Updated {new Date(alert.acknowledged_at).toLocaleString()}</p> : null}<div className="alert-actions"><Button type="button" size="sm" variant="outline" disabled={alertActionPending === alert.id || alert.status === "acknowledged"} onClick={() => alert.id && updateAlert(alert.id, "acknowledge")}>{alertActionPending === alert.id ? "Saving…" : "Acknowledge"}</Button><Button type="button" size="sm" variant="outline" disabled={alertActionPending === alert.id || alert.status === "resolved"} onClick={() => alert.id && updateAlert(alert.id, "resolve")}>Resolve</Button><Button type="button" size="sm" variant="ghost" disabled={alertActionPending === alert.id || alert.status === "dismissed"} onClick={() => alert.id && updateAlert(alert.id, "dismiss")}>Dismiss</Button>{alert.status !== "new" ? <Button type="button" size="sm" variant="ghost" disabled={alertActionPending === alert.id} onClick={() => alert.id && updateAlert(alert.id, "reopen")}>Reopen</Button> : null}</div></CardContent></Card>)}</div> : null}
      {item.href === "/smart-alerts" && data?.alerts?.length && !filteredAlerts.length ? <div className="alert-empty-filter"><p>No alerts match the selected filters.</p><Button type="button" variant="outline" size="sm" onClick={() => { setAlertSeverity("all"); setAlertStatus("all"); }}>Clear filters</Button></div> : null}
      {data?.available && isSegmentation && list.length ? (
        <Card className="panel-card">
          <CardHeader className="panel-header">
            <div>
              <CardTitle className="panel-title">{isCustomerTagging ? "Customer tags" : "RFM segments"}</CardTitle>
              <p className="panel-subtitle">{isCustomerTagging ? "Behavioral segment and transparent rule-based risk labels." : "K-Means segments using recency, frequency, and monetary value."}</p>
            </div>
            <div className="analytics-card-actions">
              <Button type="button" variant="outline" size="sm" onClick={() => downloadFromUrl(`/api/retailmind/segmentation/${encodeURIComponent(dataset!.id)}/export/csv`)}>Download full CSV</Button>
              <Button type="button" variant="outline" size="sm" onClick={() => downloadFromUrl(`/api/retailmind/segmentation/${encodeURIComponent(dataset!.id)}/export/xlsx`)}>Download XLSX</Button>
            </div>
          </CardHeader>
          <CardContent>
            {isCustomerTagging ? (
              <>
                <div className="tag-toolbar">
                  <label className="compact-field"><span><Search aria-hidden="true" /> Search customer</span><input value={tagSearch} onChange={(event) => { setTagSearch(event.target.value); setCustomerOffset(0); }} placeholder="Customer ID" /></label>
                  <label className="compact-field"><span>Tag</span><select value={tagFilter} onChange={(event) => { setTagFilter(event.target.value); setCustomerOffset(0); }}><option value="all">All tags</option>{["VIP", "Loyal", "New", "Regular", "At Risk", "Lost"].map((tag) => <option key={tag} value={tag}>{tag}</option>)}</select></label>
                  <label className="compact-field"><span>Cluster</span><select value={clusterFilter} onChange={(event) => { setClusterFilter(event.target.value); setCustomerOffset(0); }}><option value="all">All clusters</option>{Array.from({ length: Math.max(1, data?.cluster_count ?? 1) }, (_, index) => <option key={index} value={index}>Cluster {index + 1}</option>)}</select></label>
                  <label className="compact-field"><span>Sort by</span><select value={tagSort} onChange={(event) => { setTagSort(event.target.value as typeof tagSort); setCustomerOffset(0); }}><option value="monetary">Monetary value</option><option value="recency">Most recent</option><option value="frequency">Most frequent</option><option value="customer">Customer ID</option></select></label>
                </div>
                <div className="table-wrap">
                  <table className="visual-table">
                    <thead><tr><th>Customer</th><th>Tag</th><th>Segment</th><th>Cluster</th><th className="text-right">Recency (days)</th><th className="text-right">Frequency</th><th className="text-right">Monetary value</th><th>Last purchase</th></tr></thead>
                    <tbody>
                      {list.map((row, index) => (
                        <tr key={String(row.customer_id) + index}>
                          <td>{String(row.customer_id ?? "—")}</td>
                          <td>{typeof row.customer_tag === "string" ? <TagBadge tag={row.customer_tag} /> : "—"}</td>
                          <td>{String(row.segment ?? "—")}</td>
                          <td><span className="tag-badge tag-cluster">{String(row.cluster_label ?? `Cluster ${Number(row.cluster ?? 0) + 1}`)}</span></td>
                          <td className="text-right">{formatNumber(Number(row.recency_days ?? 0), 0)}</td>
                          <td className="text-right">{formatNumber(Number(row.frequency ?? 0), 0)}</td>
                          <td className="text-right">{formatCurrencyPrecise(Number(row.monetary_value ?? 0))}</td>
                          <td>{formatDate(String(row.last_purchase ?? ""))}</td>
                        </tr>
                      ))}
                      {!list.length ? <tr><td colSpan={8} className="table-empty">No customers match the selected tags, cluster or search.</td></tr> : null}
                    </tbody>
                  </table>
                </div>
                <div className="segmentation-pagination" aria-label="Customer tag pages">
                  <span>Showing {customerTotal ? customerOffset + 1 : 0}–{Math.min(customerOffset + list.length, customerTotal)} of {customerTotal.toLocaleString()} customers. Exports include the full result.</span>
                  <div>
                    <Button type="button" variant="outline" size="sm" disabled={!hasPreviousCustomerPage} onClick={() => setCustomerOffset((offset) => Math.max(0, offset - 100))}>Previous</Button>
                    <Button type="button" variant="outline" size="sm" disabled={!hasNextCustomerPage} onClick={() => setCustomerOffset((offset) => offset + 100)}>Next</Button>
                  </div>
                </div>
              </>
            ) : (
              <div className="table-wrap"><Table><TableHeader><TableRow>{fields.map((field) => <TableHead key={field}>{field.replaceAll("_", " ")}</TableHead>)}</TableRow></TableHeader><TableBody>{list.map((row, index) => <TableRow key={String(row[fields[0]]) + index}>{fields.map((field) => <TableCell key={field}>{formatSummaryCell(field, row[field])}</TableCell>)}</TableRow>)}</TableBody></Table></div>
            )}
          </CardContent>
        </Card>
      ) : null}
      {data && !data.insights?.length && !data.alerts?.length && !list.length && data.available ? <EmptyState icon={Sparkles} title="No signals found" description="The analytics engine found no matching insights, alerts, or customer groups." /> : null}
    </div>
  );
}

type ForecastResponse = {
  available: boolean;
  metric: string;
  method: string;
  history: AnalysisRow[];
  forecast: AnalysisRow[];
  metrics: Record<string, number | null>;
  notes: string[];
};

function ForecastPage({ item }: { item: NavigationItem }) {
  const { dataset } = useDataset();
  const { isAnimationActive, animationDuration, animationEasing } = useChartAnimation();
  const metricRole = item.href === "/profit-forecasting" ? "profit" : "revenue";
  const [frequency, setFrequency] = useState("Monthly");
  const [periods, setPeriods] = useState(6);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ForecastResponse | null>(null);

  async function generateForecast() {
    if (!dataset || loading) return;
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/retailmind/forecast", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ dataset_id: dataset.id, metric_role: metricRole, frequency, periods, method: "Auto (backtest)" }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "The forecasting engine could not run.");
      setResult(payload as ForecastResponse);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The forecasting engine could not run.");
    } finally {
      setLoading(false);
    }
  }

  const forecastFields = result?.forecast.length ? Object.keys(result.forecast[0]) : [];
  const forecastChartData = [
    ...(result?.history ?? []).map((row) => ({
      date: String(row.date ?? ""),
      actual: typeof row.actual === "number" ? row.actual : null,
      forecast: null,
      lower_bound: null,
      upper_bound: null,
    })),
    ...(result?.forecast ?? []).map((row) => ({
      date: String(row.date ?? ""),
      actual: null,
      forecast: typeof row.forecast === "number" ? row.forecast : null,
      lower_bound: typeof row.lower_bound === "number" ? row.lower_bound : null,
      upper_bound: typeof row.upper_bound === "number" ? row.upper_bound : null,
    })),
  ];
  const forecastExportRows = [
    ...(result?.history ?? []).map((row) => ({ date: row.date, series: "history", actual: row.actual, forecast: null, lower_bound: null, upper_bound: null })),
    ...(result?.forecast ?? []).map((row) => ({ date: row.date, series: "forecast", actual: null, forecast: row.forecast, lower_bound: row.lower_bound, upper_bound: row.upper_bound })),
  ];
  return (
    <div className="page-stack">
      <PageHeading item={item} />
      <div className="forecast-toolbar">
        <label className="compact-field"><span>Frequency</span><select aria-label="Forecast frequency" value={frequency} onChange={(event) => setFrequency(event.target.value)}><option>Daily</option><option>Weekly</option><option>Monthly</option></select></label>
        <label className="compact-field"><span>Periods</span><select aria-label="Forecast horizon" value={periods} onChange={(event) => setPeriods(Number(event.target.value))}><option value={3}>3 periods</option><option value={6}>6 periods</option><option value={12}>12 periods</option></select></label>
        <Button disabled={!dataset || loading} title={!dataset ? "Upload a dataset before generating a forecast" : undefined} onClick={generateForecast}>{loading ? "Calculating…" : "Generate forecast"}</Button>
      </div>
      {!dataset ? <EmptyState icon={Database} title="Choose a dataset to begin" description="The existing forecasting engine needs historical dates and the selected measure." action="Upload a dataset" /> : null}
      {error ? <p className="assistant-error" role="alert">{error}</p> : null}
      {result?.available ? <Card className="panel-card"><CardHeader className="panel-header"><div><CardTitle className="panel-title">Observed history and forecast</CardTitle><p className="panel-subtitle">Solid line is actual data; dashed lines show forecast and approximate interval bounds.</p></div><Button type="button" variant="outline" size="sm" onClick={() => downloadRowsAsCsv("forecast-results.csv", forecastExportRows)}>Download CSV</Button></CardHeader><CardContent><ChartContainer config={forecastChartConfig} className="forecast-chart"><LineChart accessibilityLayer key={isAnimationActive ? "animated" : "static"} data={forecastChartData} margin={{ left: 4, right: 12, top: 12, bottom: 0 }}><CartesianGrid vertical={false} strokeDasharray="3 3" /><XAxis dataKey="date" tickLine={false} axisLine={false} tickMargin={8} minTickGap={24} tickFormatter={(value) => new Date(String(value)).toLocaleDateString("en-IN", { month: "short", year: "2-digit" })} /><YAxis width={48} tickLine={false} axisLine={false} tickFormatter={(value) => new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 }).format(Number(value))} /><ChartTooltip content={<ChartTooltipContent indicator="line" formatter={(value) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(value))} />} /><Line type="monotone" dataKey="actual" stroke="var(--color-actual)" strokeWidth={2.5} dot={false} connectNulls={false} isAnimationActive={isAnimationActive} animationDuration={animationDuration} animationEasing={animationEasing} /><Line type="monotone" dataKey="forecast" stroke="var(--color-forecast)" strokeWidth={2.5} strokeDasharray="5 4" dot={false} connectNulls={false} isAnimationActive={isAnimationActive} animationDuration={animationDuration} animationEasing={animationEasing} /><Line type="monotone" dataKey="lower_bound" stroke="var(--color-lower_bound)" strokeWidth={1} strokeDasharray="2 4" dot={false} connectNulls={false} isAnimationActive={isAnimationActive} animationDuration={animationDuration} animationEasing={animationEasing} /><Line type="monotone" dataKey="upper_bound" stroke="var(--color-upper_bound)" strokeWidth={1} strokeDasharray="2 4" dot={false} connectNulls={false} isAnimationActive={isAnimationActive} animationDuration={animationDuration} animationEasing={animationEasing} /></LineChart></ChartContainer></CardContent></Card> : null}
      {result?.available ? <Card className="panel-card"><CardHeader><CardTitle className="panel-title">Forecast results</CardTitle><p className="panel-subtitle">{result.method} · {result.metric} · calculated from the uploaded history</p></CardHeader><CardContent><div className="table-wrap"><Table><TableHeader><TableRow>{forecastFields.map((field) => <TableHead key={field}>{field.replaceAll("_", " ")}</TableHead>)}</TableRow></TableHeader><TableBody>
                  {result.forecast.map((row, index) => (
                    <TableRow key={`${String(row[forecastFields[0]])}-${index}`}>{forecastFields.map((field) => <TableCell key={field}>{row[field] == null ? "—" : field === "date" && typeof row[field] === "string" ? new Date(row[field]).toLocaleDateString("en-IN", { month: "short", year: "numeric" }) : typeof row[field] === "number" ? new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(row[field] as number) : String(row[field])}</TableCell>)}</TableRow>
                  ))}
                </TableBody></Table></div><div className="forecast-metrics"><strong>Time-based holdout metrics</strong><div className="metric-grid">{Object.entries(result.metrics).filter((entry): entry is [string, number] => typeof entry[1] === "number").map(([key, value]) => <div className="metric-card" key={key}><div className="metric-content"><span className="metric-label">{key.replaceAll("_", " ")}</span><span className="metric-value">{value.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</span></div></div>)}</div></div><p className="dashboard-footnote">{result.notes.join(" ")}</p></CardContent></Card> : null}
      {result && !result.available ? <div className="backend-notice"><CircleAlert aria-hidden="true" /><span>{result.notes.join(" ")}</span></div> : null}
      <div className="info-grid info-grid-three"><InfoCard icon={Database} title="Uses uploaded history" text="Forecasts use actual dates and mapped measures from the active dataset." /><InfoCard icon={Lightbulb} title="Clear assumptions" text="Prediction intervals are approximate and are not a guarantee." /><InfoCard icon={PackageSearch} title="Existing engine" text="The Python forecasting module is preserved and remains the source of truth." /></div>
    </div>
  );
}

type ScenarioResponse = {
  available: boolean;
  baseline_sales?: number;
  baseline_profit?: number;
  projected_sales?: number;
  projected_profit?: number;
  profit_change?: number;
  rows_used?: number;
  rows_excluded?: number;
  inputs?: { discount_shift_points: number; margin_shift_points: number };
  notes: string[];
};

function ScenarioPage({ item }: { item: NavigationItem }) {
  const { dataset } = useDataset();
  const [discountShift, setDiscountShift] = useState(0);
  const [marginShift, setMarginShift] = useState(0);
  const [result, setResult] = useState<ScenarioResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function projectScenario() {
    if (!dataset || loading) return;
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/retailmind/scenarios/projection", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ dataset_id: dataset.id, discount_shift_points: discountShift, margin_shift_points: marginShift }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "The scenario could not be calculated.");
      setResult(payload as ScenarioResponse);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The scenario could not be calculated.");
    } finally {
      setLoading(false);
    }
  }

  const formatMoney = (value: number | undefined) => typeof value === "number"
    ? new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(value)
    : "—";
  const metrics = result?.available ? [
    { label: "Baseline sales", value: formatMoney(result.baseline_sales) },
    { label: "Projected sales", value: formatMoney(result.projected_sales) },
    { label: "Baseline profit", value: formatMoney(result.baseline_profit) },
    { label: "Projected profit", value: formatMoney(result.projected_profit) },
    { label: "Profit change", value: formatMoney(result.profit_change) },
  ] : [];

  return (
    <div className="page-stack">
      <PageHeading item={item} />
      {!dataset ? <EmptyState icon={Database} title="Choose a dataset to begin" description="Scenario projections need mapped sales and profit measures from an uploaded dataset." action="Upload a dataset" /> : null}
      <Card className="panel-card">
        <CardHeader><CardTitle className="panel-title">What-if assumptions</CardTitle><p className="panel-subtitle">Adjust discount and margin by percentage points against the active dataset&apos;s observed totals.</p></CardHeader>
        <CardContent>
          <div className="scenario-controls">
            <label className="scenario-slider"><span>Discount change <output>{discountShift > 0 ? "+" : ""}{discountShift} pp</output></span><input type="range" min={-100} max={100} step={1} value={discountShift} aria-label="Discount change in percentage points" onChange={(event) => setDiscountShift(Number(event.target.value))} /></label>
            <label className="scenario-slider"><span>Margin change <output>{marginShift > 0 ? "+" : ""}{marginShift} pp</output></span><input type="range" min={-100} max={100} step={1} value={marginShift} aria-label="Margin change in percentage points" onChange={(event) => setMarginShift(Number(event.target.value))} /></label>
            <Button type="button" disabled={!dataset || loading} onClick={projectScenario}>{loading ? "Calculating…" : "Calculate scenario"}</Button>
          </div>
          {error ? <p className="assistant-error" role="alert">{error}</p> : null}
        </CardContent>
      </Card>
      {result && !result.available ? <div className="backend-notice" role="status"><CircleAlert aria-hidden="true" /><span>{result.notes.join(" ")}</span></div> : null}
      {result?.available ? <Card className="panel-card"><CardHeader><CardTitle className="panel-title">Scenario projection</CardTitle><p className="panel-subtitle">Computed from {result.rows_used?.toLocaleString()} rows with valid sales and profit values.</p></CardHeader><CardContent><div className="metric-grid scenario-metrics">{metrics.map((metric) => <div className="metric-card" key={metric.label}><div className="metric-content"><span className="metric-label">{metric.label}</span><span className="metric-value">{metric.value}</span></div></div>)}</div><p className="dashboard-footnote">{result.notes.join(" ")}{result.rows_excluded ? ` ${result.rows_excluded.toLocaleString()} row(s) with invalid measure values were excluded.` : ""}</p></CardContent></Card> : null}
      <div className="info-grid info-grid-three"><InfoCard icon={Database} title="Dataset-derived" text="Baseline totals are read from the active upload; no metrics are generated from placeholders." /><InfoCard icon={Lightbulb} title="Transparent formula" text="Discount shift models revenue erosion; margin shift adjusts profit rate on projected sales." /><InfoCard icon={ShieldCheck} title="What-if, not forecast" text="This simple scenario does not estimate demand elasticity or establish causation." /></div>
    </div>
  );
}

type SavedGoal = { id: number; goal_name: string; period_start: string; period_end: string; target_sales: number; target_profit: number | null; target_category: string | null };
type GoalProgress = { id: number; name: string; category: string | null; sales: { target: number; actual: number; achievement_pct: number; remaining: number } | null; profit: { target: number; actual: number; achievement_pct: number; remaining: number } | null };

function GoalsPage({ item }: { item: NavigationItem }) {
  const { dataset } = useDataset();
  const { data, error, isLoading, mutate } = useSWR<{ goals: SavedGoal[] }>("/api/retailmind/goals", fetchJson);
  const { data: progress, error: progressError, mutate: mutateProgress } = useSWR<{ available: boolean; goals: GoalProgress[]; notes: string[] }>(dataset ? `/api/retailmind/goals/progress/${encodeURIComponent(dataset.id)}` : null, fetchJson);
  const [goalName, setGoalName] = useState("");
  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const [targetSales, setTargetSales] = useState("");
  const [targetProfit, setTargetProfit] = useState("");
  const [targetCategory, setTargetCategory] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [messageError, setMessageError] = useState(false);

  async function createGoal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    setMessage("");
    try {
      const response = await fetch("/api/retailmind/goals", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ goal_name: goalName.trim(), period_start: periodStart, period_end: periodEnd, target_sales: Number(targetSales), target_profit: targetProfit ? Number(targetProfit) : null, target_category: targetCategory.trim() || null }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "The goal could not be saved.");
      setGoalName(""); setTargetSales(""); setTargetProfit(""); setTargetCategory("");
      await Promise.all([mutate(), mutateProgress()]);
      setMessage("Goal saved to your account.");
      setMessageError(false);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "The goal could not be saved.");
      setMessageError(true);
    } finally {
      setSaving(false);
    }
  }

  async function removeGoal(goal: SavedGoal) {
    if (!window.confirm(`Delete the goal “${goal.goal_name}”?`)) return;
    try {
      const response = await fetch(`/api/retailmind/goals/${goal.id}`, { method: "DELETE" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "The goal could not be deleted.");
      await Promise.all([mutate(), mutateProgress()]);
      setMessage("Goal deleted.");
      setMessageError(false);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "The goal could not be deleted.");
      setMessageError(true);
    }
  }

  const progressById = new Map((progress?.goals ?? []).map((entry) => [entry.id, entry]));
  const money = (value: number) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(value);

  return (
    <div className="page-stack">
      <PageHeading item={item} />
      <div className="goals-layout">
        <Card className="panel-card">
          <CardHeader><CardTitle className="panel-title">Create a sales or profit target</CardTitle><p className="panel-subtitle">Targets are private to your account and stored in the existing MySQL goals table.</p></CardHeader>
          <CardContent>
            <form className="goal-form" onSubmit={createGoal}>
              <label className="goal-field goal-field-wide">Goal name<Input value={goalName} onChange={(event) => setGoalName(event.target.value)} maxLength={150} required /></label>
              <label className="goal-field">Start date<Input type="date" value={periodStart} onChange={(event) => setPeriodStart(event.target.value)} required /></label>
              <label className="goal-field">End date<Input type="date" value={periodEnd} onChange={(event) => setPeriodEnd(event.target.value)} required /></label>
              <label className="goal-field">Sales target (INR)<Input type="number" min="0.01" step="0.01" value={targetSales} onChange={(event) => setTargetSales(event.target.value)} required /></label>
              <label className="goal-field">Profit target (optional)<Input type="number" min="0" step="0.01" value={targetProfit} onChange={(event) => setTargetProfit(event.target.value)} /></label>
              <label className="goal-field goal-field-wide">Category (optional)<Input value={targetCategory} onChange={(event) => setTargetCategory(event.target.value)} maxLength={100} /></label>
              <div className="goal-form-footer"><span>Progress is calculated from the selected dataset and date range.</span><Button type="submit" disabled={saving}>{saving ? "Saving…" : "Save goal"}</Button></div>
            </form>
            {message ? <p className={cn("upload-message", messageError && "upload-message-error")} role={messageError ? "alert" : "status"}>{message}</p> : null}
          </CardContent>
        </Card>
        <Card className="panel-card">
          <CardHeader className="panel-header"><div><CardTitle className="panel-title">Saved goals</CardTitle><p className="panel-subtitle">{dataset ? `Measured against ${dataset.filename}` : "Choose a dataset to calculate progress."}</p></div><Badge variant="outline">Account-scoped</Badge></CardHeader>
          <CardContent>
            {error ? <p className="assistant-error" role="alert">{error.message}</p> : null}
            {progressError ? <p className="assistant-error" role="alert">{progressError.message}</p> : null}
            {isLoading ? <div className="loading-panel" aria-label="Loading saved goals" /> : data?.goals.length ? <div className="goal-list">{data.goals.map((goal) => {
              const actual = progressById.get(goal.id);
              const achieved = actual?.sales?.achievement_pct ?? 0;
              return <article className="goal-card" key={goal.id}><div className="goal-card-heading"><div><strong>{goal.goal_name}</strong><span>{new Date(`${goal.period_start}T00:00:00`).toLocaleDateString()} – {new Date(`${goal.period_end}T00:00:00`).toLocaleDateString()}{goal.target_category ? ` · ${goal.target_category}` : ""}</span></div><Button variant="ghost" size="sm" aria-label={`Delete ${goal.goal_name}`} onClick={() => removeGoal(goal)}>Delete</Button></div><div className="goal-progress-label"><span>Sales</span><strong>{actual?.sales ? `${money(actual.sales.actual)} of ${money(actual.sales.target)}` : `${money(Number(goal.target_sales))} target`}</strong></div><div className="goal-progress-track" role="progressbar" aria-label={`${goal.goal_name} sales achievement`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.max(0, Math.min(100, achieved))}><span style={{ width: `${Math.max(0, Math.min(100, achieved))}%` }} /></div><div className="goal-progress-caption">{dataset && actual?.sales ? `${achieved.toFixed(1)}% achieved · ${money(actual.sales.remaining)} remaining` : "Upload and select a dataset to calculate actual progress."}{goal.target_profit != null ? ` · Profit target ${money(Number(goal.target_profit))}` : ""}</div></article>;
            })}</div> : <EmptyState icon={Target} title="No goals saved" description="Create a target above to track sales or profit performance against your real dataset." />}
            {progress?.notes?.length ? <p className="dashboard-footnote">{progress.notes.join(" ")}</p> : null}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

const reportTiles = [
  { name: "Excel workbook", format: "XLSX", endpoint: "xlsx", icon: FileSpreadsheet, href: "/excel-export", description: "Source data, field mapping, and data-quality summary." },
  { name: "Business report", format: "PDF", endpoint: "pdf", icon: FileText, href: "/pdf-export", description: "Executive summary with verified insights and forecast context." },
  { name: "Power BI project", format: "PBIP / TMDL / PBIR", endpoint: "pbip", icon: FileBarChart2, href: "/pbip-export", description: "Editable PBIP project package with structural validation." },
  { name: "Markdown report", format: "Markdown", endpoint: "md", icon: FileText, href: "/markdown-export", description: "Portable Markdown table with active date-range details." },
];

type SavedReport = { id: number; report_name: string; report_type: string; filters: { dataset_id?: string; export_format?: string; date_from?: string; date_to?: string }; created_at: string };

function ReportsPage({ item }: { item: NavigationItem }) {
  const { dataset } = useDataset();
  const isSavedReports = item.href === "/saved-reports";
  const isBuilder = item.href === "/report-builder";
  const selected = item.href === "/excel-export" ? reportTiles.slice(0, 1) : item.href === "/pdf-export" ? reportTiles.slice(1, 2) : item.href === "/power-bi-export" || item.href === "/pbip-export" ? reportTiles.slice(2, 3) : item.href === "/markdown-export" ? reportTiles.slice(3, 4) : reportTiles;
  const initialFormat = selected[0]?.endpoint ?? "xlsx";
  const inferredType = item.href.includes("sales") ? "sales" : item.href.includes("profit") ? "profitability" : item.href.includes("product") ? "products" : item.href.includes("customer") ? "customers" : item.href.includes("inventory") ? "inventory" : "overview";
  const [reportName, setReportName] = useState("");
  const [builderType, setBuilderType] = useState("overview");
  const [builderFormat, setBuilderFormat] = useState("xlsx");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [reportSearch, setReportSearch] = useState("");
  const [reportTypeFilter, setReportTypeFilter] = useState("all");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [messageError, setMessageError] = useState(false);
  const { data: savedData, error: savedError, isLoading: reportsLoading, mutate: mutateReports } = useSWR<{ reports: SavedReport[] }>(isSavedReports ? "/api/retailmind/reports" : null, fetchJson);

  const reportType = isBuilder ? builderType : inferredType;
  const format = isBuilder ? builderFormat : initialFormat;
  const dateRangeInvalid = Boolean(dateFrom && dateTo && dateFrom > dateTo);
  const savedTypes = Array.from(new Set((savedData?.reports ?? []).map((report) => report.report_type))).sort();
  const filteredReports = (savedData?.reports ?? []).filter((report) =>
    report.report_name.toLowerCase().includes(reportSearch.trim().toLowerCase())
    && (reportTypeFilter === "all" || report.report_type === reportTypeFilter)
  );

  function download(datasetId: string, endpoint: string, filters: { date_from?: string; date_to?: string } = {}) {
    const params = new URLSearchParams();
    if (filters.date_from) params.set("date_from", filters.date_from);
    if (filters.date_to) params.set("date_to", filters.date_to);
    const query = params.toString();
    const link = document.createElement("a");
    link.href = `/api/retailmind/export/${encodeURIComponent(datasetId)}/${endpoint}${query ? `?${query}` : ""}`;
    link.download = "";
    document.body.append(link);
    link.click();
    link.remove();
  }

  async function saveReport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!dataset || saving) return;
    setSaving(true);
    setMessage("");
    try {
      const response = await fetch("/api/retailmind/reports", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ report_name: reportName.trim(), report_type: reportType, filters: { dataset_id: dataset.id, export_format: format, ...(dateFrom ? { date_from: dateFrom } : {}), ...(dateTo ? { date_to: dateTo } : {}) } }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Report metadata could not be saved.");
      setReportName("");
      setMessage("Report configuration saved to your account.");
      setMessageError(false);
      await mutateReports();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Report metadata could not be saved.");
      setMessageError(true);
    } finally {
      setSaving(false);
    }
  }

  async function deleteReport(report: SavedReport) {
    try {
      const response = await fetch(`/api/retailmind/reports/${report.id}`, { method: "DELETE" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "The report could not be deleted.");
      await mutateReports();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "The report could not be deleted.");
      setMessageError(true);
    }
  }

  return (
    <div className="page-stack">
      <PageHeading item={item} />
      {!isSavedReports ? <div className="report-filter-toolbar"><label className="compact-field"><span>From date</span><Input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} aria-label="Report start date" /></label><label className="compact-field"><span>To date</span><Input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} aria-label="Report end date" /></label><Button type="button" variant="ghost" size="sm" disabled={!dateFrom && !dateTo} onClick={() => { setDateFrom(""); setDateTo(""); }}>Clear dates</Button></div> : null}
      {dateRangeInvalid ? <p className="assistant-error" role="alert">The report start date must be on or before its end date.</p> : null}
      {isSavedReports ? (
        <Card className="panel-card"><CardHeader><CardTitle className="panel-title">Saved report configurations</CardTitle><p className="panel-subtitle">Saved filters and export choices are stored as metadata in your account.</p></CardHeader><CardContent>
          {savedError ? <p className="assistant-error" role="alert">{savedError.message}</p> : null}
          <div className="saved-report-toolbar"><label htmlFor="saved-report-search">Search reports<Input id="saved-report-search" value={reportSearch} onChange={(event) => setReportSearch(event.target.value)} placeholder="Search by report name" /></label><label className="compact-field"><span>Report type</span><select value={reportTypeFilter} onChange={(event) => setReportTypeFilter(event.target.value)}><option value="all">All types</option>{savedTypes.map((type) => <option key={type} value={type}>{type}</option>)}</select></label></div>
          {reportsLoading ? <div className="loading-panel" aria-label="Loading saved reports" /> : filteredReports.length ? <div className="saved-report-list">{filteredReports.map((report) => <article className="saved-report-row" key={report.id}><span className="report-icon"><FileBarChart2 aria-hidden="true" /></span><div><strong>{report.report_name}</strong><span>{report.report_type} · {report.filters?.date_from || report.filters?.date_to ? `${report.filters.date_from || "Beginning"} – ${report.filters.date_to || "Present"} · ` : ""}{report.created_at ? new Date(report.created_at).toLocaleDateString() : "Saved"}</span></div><div className="saved-report-actions"><Button type="button" variant="outline" size="sm" disabled={!report.filters?.dataset_id || !report.filters?.export_format} onClick={() => download(report.filters.dataset_id!, report.filters.export_format!, { date_from: report.filters.date_from, date_to: report.filters.date_to })}>Export</Button><Button type="button" variant="ghost" size="sm" aria-label={`Delete ${report.report_name}`} onClick={() => deleteReport(report)}>Delete</Button></div></article>)}</div> : reportSearch || reportTypeFilter !== "all" ? <EmptyState icon={FileBarChart2} title="No matching reports" description="Clear the search or choose another report type." /> : <EmptyState icon={FileBarChart2} title="No saved reports yet" description="Build a report or save one from an export page. Configurations remain scoped to your account." action="Open report builder" href="/report-builder" />}
        </CardContent></Card>
      ) : (
        <>
          {!dataset ? <EmptyState icon={Database} title="Choose a dataset to export" description="Upload a CSV or Excel file before generating reports." action="Upload a dataset" /> : null}
          {isBuilder ? <Card className="panel-card"><CardHeader><CardTitle className="panel-title">Configure a report</CardTitle><p className="panel-subtitle">Choose an output and save the settings to your account.</p></CardHeader><CardContent><div className="report-builder-fields"><label className="goal-field">Report type<select value={builderType} onChange={(event) => setBuilderType(event.target.value)}><option value="overview">Overview</option><option value="sales">Sales</option><option value="profitability">Profitability</option><option value="products">Products</option><option value="customers">Customers</option><option value="inventory">Inventory</option><option value="forecast">Forecast</option><option value="custom">Custom</option></select></label><label className="goal-field">Export format<select value={builderFormat} onChange={(event) => setBuilderFormat(event.target.value)}><option value="xlsx">Excel workbook</option><option value="pdf">PDF report</option><option value="pbip">Power BI project</option><option value="csv">CSV data</option><option value="md">Markdown report</option></select></label><Button type="button" variant="outline" disabled={!dataset || dateRangeInvalid} onClick={() => dataset && download(dataset.id, builderFormat, { date_from: dateFrom, date_to: dateTo })}>Generate export</Button></div></CardContent></Card> : null}
          <div className="report-grid">{selected.map(({ name, format: tileFormat, endpoint, icon: Icon, href, description }) => <Card className="panel-card report-tile" key={name}><CardContent><span className="report-icon"><Icon aria-hidden="true" /></span><div className="report-tile-heading"><h2>{name}</h2><Badge variant="secondary">{tileFormat}</Badge></div><p>{description}</p><Button type="button" variant="outline" size="sm" disabled={!dataset || dateRangeInvalid} title={!dataset ? "Upload a dataset before generating this export" : dateRangeInvalid ? "Choose a valid date range" : undefined} onClick={() => dataset && download(dataset.id, endpoint, { date_from: dateFrom, date_to: dateTo })}>Download {tileFormat}</Button>{item.href !== href ? <Link className="report-detail-link" href={href}>Open export page<ArrowRight aria-hidden="true" /></Link> : null}</CardContent></Card>)}</div>
          <Card className="panel-card"><CardHeader><CardTitle className="panel-title">Save this configuration</CardTitle><p className="panel-subtitle">This saves report metadata and filters, not a copy of the exported file.</p></CardHeader><CardContent><form className="save-report-form" onSubmit={saveReport}><label htmlFor="report-name">Report name</label><Input id="report-name" value={reportName} onChange={(event) => setReportName(event.target.value)} maxLength={150} placeholder="Monthly retail performance" required /><Button type="submit" variant="outline" disabled={!dataset || saving || dateRangeInvalid}>{saving ? "Saving…" : "Save report"}</Button></form>{message ? <p className={cn("upload-message", messageError && "upload-message-error")} role={messageError ? "alert" : "status"}>{message}</p> : null}</CardContent></Card>
        </>
      )}
    </div>
  );
}

function DataConnectionsPage({ item }: { item: NavigationItem }) {
  const { data: health, error, isLoading } = useSWR<{ status: string; service: string; storage: string }>("/api/retailmind/health", fetchJson);
  return (
    <div className="page-stack">
      <PageHeading item={item} />
      <div className="settings-grid">
        <Card className="panel-card"><CardHeader className="panel-header"><div><CardTitle className="panel-title">Python analytics service</CardTitle><p className="panel-subtitle">The existing Streamlit app remains available; Next.js calls this additive FastAPI adapter.</p></div><Badge variant={health?.status === "ok" ? "secondary" : "outline"}>{isLoading ? "Checking" : error ? "Unavailable" : "Running"}</Badge></CardHeader><CardContent>
          {error ? <p className="assistant-error" role="alert">{error.message}</p> : null}
          <div className="connection-detail"><span className="connection-detail-icon"><Database aria-hidden="true" /></span><div><strong>Account-scoped MySQL data</strong><p>Authentication, owner monitoring, saved reports, goals, preferences, upload history, and persistent upload metadata use the existing parameterized service methods.</p></div></div>
          <div className="connection-detail"><span className="connection-detail-icon"><Wrench aria-hidden="true" /></span><div><strong>Preserved backend boundary</strong><p>Dashboard calculations, forecasting, segmentation, inventory recommendations, AI answers, RAG retrieval, and exports continue to call the original Python modules. Streamlit was not replaced.</p></div></div>
          <div className="backend-contract"><span>API service status</span><code>{health?.service ?? "Not verified"} · {health?.storage ?? "MySQL-backed account storage"}</code></div>
          <p className="dashboard-footnote">The preview API listens on the local workspace. A production deployment must host the Python service and its user-scoped file volume alongside the Next.js app.</p>
        </CardContent></Card>
        <Card className="panel-card"><CardHeader><CardTitle className="panel-title">Implemented capabilities</CardTitle><p className="panel-subtitle">No database migrations run automatically.</p></CardHeader><CardContent><div className="feature-list"><p><ShieldCheck aria-hidden="true" /> HttpOnly, hashed-session authentication</p><p><Database aria-hidden="true" /> User-scoped upload files and history</p><p><FileBarChart2 aria-hidden="true" /> Saved report metadata and exports</p><p><Target aria-hidden="true" /> Private sales and profit goals</p><p><Users aria-hidden="true" /> Owner-only account, session, and audit controls</p><p><Sparkles aria-hidden="true" /> Local document retrieval with source excerpts</p></div><Link href="/security" className="text-action">Review account security <ArrowRight aria-hidden="true" /></Link></CardContent></Card>
      </div>
    </div>
  );
}

function ProfileSettingsPage({ item }: { item: NavigationItem }) {
  const { session } = useSession();
  const { mutate } = useSWRConfig();
  const [fullName, setFullName] = useState(session?.user.full_name ?? "");
  const [email, setEmail] = useState(session?.user.email ?? "");
  const [phone, setPhone] = useState(session?.user.phone ?? "");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [messageError, setMessageError] = useState(false);

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session || saving) return;
    setSaving(true); setMessage("");
    try {
      const response = await fetch("/api/retailmind/auth/profile", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ full_name: fullName.trim(), email: email.trim(), phone: phone.trim() || null }) });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Profile could not be saved.");
      await mutate("/api/retailmind/auth/session");
      setMessage("Profile saved."); setMessageError(false);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Profile could not be saved."); setMessageError(true);
    } finally { setSaving(false); }
  }

  return <div className="page-stack"><PageHeading item={item} /><Card className="panel-card profile-settings-card"><CardHeader><CardTitle className="panel-title">Account profile</CardTitle><p className="panel-subtitle">Your profile is managed by the existing MySQL-backed account service.</p></CardHeader><CardContent><form className="profile-form" onSubmit={saveProfile}><label>Full name<Input value={fullName} onChange={(event) => setFullName(event.target.value)} maxLength={150} required /></label><label>Email address<Input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} maxLength={254} required /></label><label>Phone number<Input type="tel" autoComplete="tel" value={phone} onChange={(event) => setPhone(event.target.value)} maxLength={32} /></label><div className="profile-form-footer"><span>{session?.user.account_status === "active" ? "Active account" : "Account status unavailable"}</span><Button type="submit" disabled={saving}>{saving ? "Saving…" : "Save profile"}</Button></div></form>{message ? <p className={cn("upload-message", messageError && "upload-message-error")} role={messageError ? "alert" : "status"}>{message}</p> : null}</CardContent></Card></div>;
}

function AccountSecurityPage({ item }: { item: NavigationItem }) {
  const router = useRouter();
  const { session } = useSession();
  const { mutate } = useSWRConfig();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [messageError, setMessageError] = useState(false);

  async function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;
    if (newPassword !== confirmPassword) { setMessage("The new passwords do not match."); setMessageError(true); return; }
    setSaving(true); setMessage("");
    try {
      const response = await fetch("/api/retailmind/auth/password", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }) });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Password could not be updated.");
      setCurrentPassword(""); setNewPassword(""); setConfirmPassword("");
      await mutate("/api/retailmind/auth/session", null, { revalidate: false });
      router.replace("/login"); router.refresh();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Password could not be updated."); setMessageError(true);
    } finally { setSaving(false); }
  }

  return <div className="page-stack"><PageHeading item={item} /><div className="settings-grid"><Card className="panel-card"><CardHeader><CardTitle className="panel-title">Change password</CardTitle><p className="panel-subtitle">Use a new password with at least 12 characters. Other sessions will be invalidated.</p></CardHeader><CardContent><form className="profile-form" onSubmit={changePassword}><label>Current password<Input type="password" autoComplete="current-password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required /></label><label>New password<Input type="password" autoComplete="new-password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} minLength={12} required /></label><label>Confirm new password<Input type="password" autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} minLength={12} required /></label><Button type="submit" disabled={saving}>{saving ? "Updating…" : "Update password"}</Button></form>{message ? <p className={cn("upload-message", messageError && "upload-message-error")} role={messageError ? "alert" : "status"}>{message}</p> : null}</CardContent></Card><Card className="panel-card"><CardHeader><CardTitle className="panel-title">Session security</CardTitle><p className="panel-subtitle">Sessions are stored as hashed secrets and revalidated against account status.</p></CardHeader><CardContent><div className="feature-list"><p><LockKeyhole aria-hidden="true" /> Signed in as {session?.user.email ?? "account unavailable"}</p><p><ShieldCheck aria-hidden="true" /> Passwords are processed by the existing Argon2id service.</p><p><Users aria-hidden="true" /> Owner administrators can revoke other active sessions from the owner console.</p></div>{session?.role === "owner_admin" ? <Link href="/owner-admin" className="text-action">Open owner console <ArrowRight aria-hidden="true" /></Link> : null}</CardContent></Card></div></div>;
}

function PreferencesPage({ item }: { item: NavigationItem }) {
  const { data, error, isLoading, mutate } = useSWR<{ preferences: { currency: string; date_format: string; default_period: string; compact_mode: boolean } }>("/api/retailmind/preferences", fetchJson);
  const [preferenceOverrides, setPreferenceOverrides] = useState<Partial<{ currency: string; date_format: string; default_period: string; compact_mode: boolean }>>({});
  const preferences = { currency: "INR", date_format: "DD MMM YYYY", default_period: "30d", compact_mode: false, ...data?.preferences, ...preferenceOverrides };
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [messageError, setMessageError] = useState(false);
  const { enabled: animationsEnabled, setEnabled: setAnimationsEnabled, systemReducedMotion } = useAnimationPreference();

  async function savePreferences(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true); setMessage("");
    try {
      const response = await fetch("/api/retailmind/preferences", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify(preferences) });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Preferences could not be saved.");
      await mutate(); setMessage("Preferences saved to your account."); setMessageError(false);
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : "Preferences could not be saved."); setMessageError(true); }
    finally { setSaving(false); }
  }

  return <div className="page-stack"><PageHeading item={item} /><Card className="panel-card profile-settings-card"><CardHeader><CardTitle className="panel-title">Workspace preferences</CardTitle><p className="panel-subtitle">Preferences are saved in the existing user_preferences table.</p></CardHeader><CardContent>{error ? <p className="assistant-error" role="alert">{error.message}</p> : null}{isLoading ? <div className="loading-panel" aria-label="Loading preferences" /> : <form className="preferences-form" onSubmit={savePreferences}><label>Currency<select value={preferences.currency} onChange={(event) => setPreferenceOverrides((current) => ({ ...current, currency: event.target.value }))}><option value="INR">INR · Indian rupee</option><option value="USD">USD · US dollar</option><option value="EUR">EUR · Euro</option><option value="GBP">GBP · Pound sterling</option></select></label><label>Date format<select value={preferences.date_format} onChange={(event) => setPreferenceOverrides((current) => ({ ...current, date_format: event.target.value }))}><option>DD MMM YYYY</option><option>MM/DD/YYYY</option><option>YYYY-MM-DD</option></select></label><label>Default reporting period<select value={preferences.default_period} onChange={(event) => setPreferenceOverrides((current) => ({ ...current, default_period: event.target.value }))}><option value="7d">Last 7 days</option><option value="30d">Last 30 days</option><option value="90d">Last 90 days</option><option value="12m">Last 12 months</option></select></label><label className="compact-toggle"><input type="checkbox" checked={preferences.compact_mode} onChange={(event) => setPreferenceOverrides((current) => ({ ...current, compact_mode: event.target.checked }))} /> Use compact data tables</label><label className="compact-toggle"><input type="checkbox" checked={animationsEnabled && !systemReducedMotion} disabled={systemReducedMotion} onChange={(event) => setAnimationsEnabled(event.target.checked)} /> Animate charts and KPI counters</label><p className="preferences-note">{systemReducedMotion ? "Your system requests reduced motion, so chart animations stay off." : "Chart animations are stored on this device and apply immediately. They also pause automatically for reduced-motion users."}</p><Button type="submit" disabled={saving}>{saving ? "Saving…" : "Save preferences"}</Button></form>}{message ? <p className={cn("upload-message", messageError && "upload-message-error")} role={messageError ? "alert" : "status"}>{message}</p> : null}</CardContent></Card></div>;
}

function OwnerAdminPage({ item }: { item: NavigationItem }) {
  const { data, error, isLoading, mutate } = useSWR<{ owner: Record<string, string> | null; accounts: Record<string, string | number>[]; sessions: Record<string, string | number | null>[]; events: Record<string, string | number>[]; event_counts: Record<string, string | number>[] }>("/api/retailmind/owner-admin/overview", fetchJson);
  const [actionError, setActionError] = useState("");
  async function revokeSession(id: string) {
    setActionError("");
    try {
      const response = await fetch(`/api/retailmind/owner-admin/sessions/${encodeURIComponent(id)}/revoke`, { method: "POST" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "The session could not be revoked.");
      await mutate();
    } catch (reason) { setActionError(reason instanceof Error ? reason.message : "The session could not be revoked."); }
  }
  const dateCell = (value: unknown) => value ? new Date(String(value)).toLocaleString() : "—";
  return <div className="page-stack"><PageHeading item={item} /><Card className="panel-card"><CardHeader><CardTitle className="panel-title">Owner administrator console</CardTitle><p className="panel-subtitle">Read-only account and audit monitoring; session revocation is the only available state-changing action.</p></CardHeader><CardContent>{error ? <div className="backend-notice" role="alert"><ShieldCheck aria-hidden="true" /><span>{error.message}</span></div> : null}{actionError ? <p className="assistant-error" role="alert">{actionError}</p> : null}{isLoading ? <div className="loading-panel" aria-label="Loading owner controls" /> : data ? <><div className="owner-summary"><div><span>Assigned owner</span><strong>{data.owner?.full_name ?? "No owner assigned"}</strong><small>{data.owner?.email ?? "Use the existing controlled bootstrap procedure."}</small></div><div><span>Accounts</span><strong>{data.accounts.length}</strong></div><div><span>Sessions</span><strong>{data.sessions.filter((session) => !session.revoked_at).length}</strong></div><div><span>Audit events</span><strong>{data.events.length}</strong></div></div><h2 className="settings-section-title">Accounts</h2><div className="table-wrap"><Table><TableHeader><TableRow><TableHead>Name</TableHead><TableHead>Email</TableHead><TableHead>Role</TableHead><TableHead>Status</TableHead><TableHead>Last sign in</TableHead></TableRow></TableHeader><TableBody>{data.accounts.map((account) => <TableRow key={String(account.id)}><TableCell>{String(account.full_name)}</TableCell><TableCell>{String(account.email)}</TableCell><TableCell>{String(account.assigned_role)}</TableCell><TableCell>{String(account.account_status)}</TableCell><TableCell>{dateCell(account.last_login_at)}</TableCell></TableRow>)}</TableBody></Table></div><h2 className="settings-section-title">Active sessions</h2><div className="table-wrap"><Table><TableHeader><TableRow><TableHead>Account</TableHead><TableHead>Last activity</TableHead><TableHead>Expires</TableHead><TableHead>Status</TableHead><TableHead>Action</TableHead></TableRow></TableHeader><TableBody>{data.sessions.map((session) => <TableRow key={String(session.id)}><TableCell>{String(session.email)}</TableCell><TableCell>{dateCell(session.last_activity_at)}</TableCell><TableCell>{dateCell(session.expires_at)}</TableCell><TableCell>{session.revoked_at ? "Revoked" : "Active"}</TableCell><TableCell>{session.revoked_at ? "—" : <Button variant="outline" size="sm" onClick={() => revokeSession(String(session.id))}>Revoke</Button>}</TableCell></TableRow>)}</TableBody></Table></div><h2 className="settings-section-title">Recent audit activity</h2><div className="table-wrap"><Table><TableHeader><TableRow><TableHead>Event</TableHead><TableHead>Status</TableHead><TableHead>Account ID</TableHead><TableHead>Time</TableHead></TableRow></TableHeader><TableBody>{data.events.map((event) => <TableRow key={String(event.id)}><TableCell>{String(event.event_type)}</TableCell><TableCell>{String(event.status)}</TableCell><TableCell>{String(event.user_id ?? "System")}</TableCell><TableCell>{dateCell(event.created_at)}</TableCell></TableRow>)}</TableBody></Table></div></> : null}</CardContent></Card></div>;
}


export function FeaturePage({ item }: { item: NavigationItem & { group: string } }) {
  if (item.href === "/upload") return <UploadPage item={item} />;
  if (item.href === "/visual-analytics") return <VisualAnalyticsPage item={item} />;
  if (item.href === "/india-map") return <IndiaMapPage item={item} />;
  if (item.href === "/city-analytics") return <CityAnalyticsPage item={item} />;
  if (item.href === "/datasets") return <DatasetPage item={item} />;
  if (item.href === "/activity") return <ActivityPage item={item} />;
  if (item.href === "/goals") return <GoalsPage item={item} />;
  if (item.href === "/owner-admin") return <OwnerAdminPage item={item} />;
  if (item.href === "/profile") return <ProfileSettingsPage item={item} />;
  if (item.href === "/account-settings" || item.href === "/security") return <AccountSecurityPage item={item} />;
  if (item.href === "/preferences") return <PreferencesPage item={item} />;
  if (item.href === "/data-connections") return <DataConnectionsPage item={item} />;
  if (item.href === "/stock-recommendations") return <StockRecommendationsPage item={item} />;
  if (item.href === "/performance-predictions") return <ScenarioPage item={item} />;
  if (item.group === "Business analytics") return <AnalyticsPage item={item} />;
  if (item.group === "AI intelligence") return <IntelligencePage item={item} />;
  if (item.group === "Predictive analytics") return <ForecastPage item={item} />;
  if (item.group === "Reports & exports") return <ReportsPage item={item} />;
  return <DataConnectionsPage item={item} />;
}
