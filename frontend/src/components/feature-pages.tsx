"use client";

import { useRef, useState, type ChangeEvent, type DragEvent, type FormEvent } from "react";
import { AnalyticsDateFilter } from "@/components/analytics-date-filter";
import { useReducedMotion } from "@/lib/use-reduced-motion";
import useSWR, { useSWRConfig } from "swr";
import Link from "next/link";
import { useRouter } from "next/navigation";
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
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";
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
      setMessage("Dataset processed and saved to your account.");
      setMessageIsError(false);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      router.push("/overview");
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
            <input ref={inputRef} className="sr-only" type="file" accept=".csv,.xlsx,.xls,.xlsm" aria-label="Choose a CSV or Excel dataset" onChange={handleFileChange} />
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
type IntelligenceResult = {
  available: boolean;
  insights?: string[];
  alerts?: {
    id?: string; title: string; description: string; severity: string; suggestion: string; metric: string;
    status?: "new" | "acknowledged" | "dismissed"; current_value?: number | null; previous_value?: number | null;
    pct_change?: number | null; comparison_period?: string; scope?: string; evidence?: Record<string, unknown>;
    acknowledged_at?: string | null; detected_at?: string;
  }[];
  summary?: AnalysisRow[];
  customers?: AnalysisRow[];
  customer_total?: number;
  customer_offset?: number;
  customer_limit?: number;
  notes?: string[];
};

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
  const fields = rows.length ? Object.keys(rows[0]) : [];

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
      {data?.available && rows.length ? <Card className="panel-card"><CardHeader className="panel-header"><div><CardTitle className="panel-title">{inventory ? "Replenishment recommendations" : "Calculated results"}</CardTitle><p className="panel-subtitle">{rows.length.toLocaleString()} {inventory ? "recommendations" : "groups"} from the existing Python analytics engine</p></div><div className="analytics-card-actions"><Badge variant="secondary">Live dataset</Badge>{inventory ? <Button type="button" variant="outline" size="sm" onClick={() => downloadRowsAsCsv("inventory-recommendations.csv", rows)}>Download CSV</Button> : null}</div></CardHeader><CardContent><div className="table-wrap"><Table><TableHeader><TableRow>{fields.map((field) => <TableHead key={field}>{field.replaceAll("_", " ")}</TableHead>)}</TableRow></TableHeader><TableBody>{rows.slice(0, 100).map((row, index) => <TableRow key={String(row[fields[0]]) + index}>{fields.map((field) => <TableCell key={field}>{formatCell(field, row[field])}</TableCell>)}</TableRow>)}</TableBody></Table></div>{data.assumptions?.length ? <div className="inventory-assumptions">{data.assumptions.map((assumption) => <p key={assumption}>{assumption}</p>)}</div> : null}</CardContent></Card> : null}
      {data?.notes?.length ? <p className="dashboard-footnote">{data.notes.join(" ")}</p> : null}
    </div>
  );
}

function InfoCard({ icon: Icon, title, text }: { icon: typeof Check; title: string; text: string }) {
  return <Card className="info-card"><CardContent><span className="info-icon"><Icon aria-hidden="true" /></span><strong>{title}</strong><p>{text}</p></CardContent></Card>;
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
            <div className="assistant-composer"><textarea id="assistant-question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder={dataset ? "Ask about the active dataset…" : "Upload a dataset to start asking questions"} disabled={!dataset || asking} rows={2} /><Button type="submit" disabled={!dataset || !question.trim() || asking}>{asking ? "Thinking…" : "Ask"}</Button></div>
          </form>
          {error ? <p className="assistant-error" role="alert">{error}</p> : null}
          {answer ? <div className="assistant-answer" role="status"><div><strong>Verified answer</strong>{answer.verified ? <Badge variant="secondary">Data-backed</Badge> : null}</div><p>{answer.text}</p>{answer.sources.length ? <ul>{answer.sources.map((source) => <li key={source}>{source}</li>)}</ul> : null}</div> : null}
          {!dataset ? <p className="assistant-note"><LockKeyhole aria-hidden="true" /> Upload a dataset before sending questions.</p> : null}
        </CardContent></Card>
        <Card className="panel-card evidence-card"><CardHeader><CardTitle className="panel-title">Answer sources</CardTitle><p className="panel-subtitle">Evidence for generated responses.</p></CardHeader><CardContent><EmptyState icon={Search} title="Source records are available" description="Answers are computed from your active dataset. Document citations are part of the separate RAG workspace." action="Open RAG assistant" href="/rag-assistant" /></CardContent></Card>
      </div>
    </div>
  );
}

type RAGDocument = { name: string; characters: number; chunks: number };
type RAGSource = { doc_name: string; chunk_index: number; score: number; excerpt: string };
type RAGResponse = { text: string; verified_retrieval: boolean; sources: RAGSource[]; note: string; used_llm: boolean };

function RagAssistantPage({ item }: { item: NavigationItem }) {
  const { data, error: loadError, isLoading, mutate } = useSWR<{ documents: RAGDocument[]; storage: string }>("/api/retailmind/ai/rag/documents", fetchJson);
  const [file, setFile] = useState<File | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<RAGResponse | null>(null);
  const [uploading, setUploading] = useState(false);
  const [asking, setAsking] = useState(false);
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");

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
        body: JSON.stringify({ question: question.trim() }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "The retrieval assistant could not answer.");
      setAnswer(payload as RAGResponse);
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
            {answer ? <div className="rag-answer" role="status"><div className="rag-answer-heading"><strong>Retrieved answer</strong><Badge variant="secondary">{answer.verified_retrieval ? "Source-backed" : "Unverified"}</Badge></div><p>{answer.text}</p><small>{answer.note}</small>{answer.sources.length ? <div className="rag-sources"><h3>Sources</h3>{answer.sources.map((source) => <article key={`${source.doc_name}-${source.chunk_index}`}><strong>{source.doc_name} · chunk {source.chunk_index + 1}</strong><span>Relevance {source.score.toFixed(2)}</span><p>{source.excerpt}</p></article>)}</div> : null}</div> : null}
          </CardContent>
        </Card>
        <Card className="panel-card rag-documents-card">
          <CardHeader><CardTitle className="panel-title">Knowledge sources</CardTitle><p className="panel-subtitle">Up to 25 documents, 5 MB each.</p></CardHeader>
          <CardContent>
            <form className="rag-upload-form" onSubmit={uploadDocument}>
              <label htmlFor="rag-file">Add a document</label>
              <input id="rag-file" type="file" accept=".txt,.md,.csv,.json,.pdf,.docx" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
              <Button type="submit" variant="outline" size="sm" disabled={!file || uploading}>{uploading ? "Indexing…" : "Index document"}</Button>
            </form>
            <div className="rag-document-list" aria-live="polite">
              {data?.documents.length ? data.documents.map((document) => <div className="rag-document-row" key={document.name}><span className="file-type-icon"><FileText aria-hidden="true" /></span><div><strong>{document.name}</strong><span>{document.chunks} chunks · {document.characters.toLocaleString()} characters</span></div><Button variant="ghost" size="sm" aria-label={`Remove ${document.name}`} onClick={() => removeDocument(document.name)}>Remove</Button></div>) : !isLoading ? <EmptyState icon={FileText} title="No documents indexed" description="Add a text, spreadsheet, JSON, PDF, or DOCX file to create a private retrieval index." /> : null}
            </div>
            <p className="rag-storage-note"><ShieldCheck aria-hidden="true" /> This mirrors the existing Streamlit session-scoped RAG store. The index clears when the Python service restarts.</p>
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
  const customerOffset = customerPage.datasetId === dataset?.id ? customerPage.offset : 0;
  function setCustomerOffset(nextOffset: number | ((currentOffset: number) => number)) {
    const currentOffset = customerPage.datasetId === dataset?.id ? customerPage.offset : 0;
    setCustomerPage({
      datasetId: dataset?.id ?? "",
      offset: typeof nextOffset === "function" ? nextOffset(currentOffset) : nextOffset,
    });
  }
  const segmentationQuery = isCustomerTagging ? `?offset=${customerOffset}&limit=100` : "";
  const endpoint = !dataset || item.href === "/assistant" || isRag ? null
    : isSegmentation ? `/api/retailmind/segmentation/${encodeURIComponent(dataset.id)}${segmentationQuery}`
      : item.href === "/smart-alerts" ? `/api/retailmind/ai/alerts/${encodeURIComponent(dataset.id)}`
        : `/api/retailmind/ai/insights/${encodeURIComponent(dataset.id)}`;
  const { data, error, isLoading } = useSWR<IntelligenceResult>(endpoint, fetchJson);
  const [alertSeverity, setAlertSeverity] = useState("all");
  const [alertStatus, setAlertStatus] = useState("all");
  const filteredAlerts = (data?.alerts ?? []).filter((alert) =>
    (alertSeverity === "all" || alert.severity === alertSeverity)
    && (alertStatus === "all" || alert.status === alertStatus)
  );

  if (item.href === "/assistant") return <AssistantWorkspace item={item} />;
  if (isRag) return <RagAssistantPage item={item} />;

  const list = isSegmentation ? (isCustomerTagging ? data?.customers ?? [] : data?.summary ?? []) : [];
  const fields = list.length ? Object.keys(list[0]) : [];
  const customerTotal = data?.customer_total ?? list.length;
  const hasPreviousCustomerPage = customerOffset > 0;
  const hasNextCustomerPage = customerOffset + list.length < customerTotal;
  return (
    <div className="page-stack">
      <PageHeading item={item} />
      {item.href === "/smart-alerts" && data?.alerts ? <div className="alert-filter-toolbar" aria-label="Filter smart alerts"><label className="compact-field"><span>Severity</span><select value={alertSeverity} onChange={(event) => setAlertSeverity(event.target.value)}><option value="all">All severities</option><option value="critical">Critical</option><option value="warning">Warning</option><option value="info">Info</option></select></label><label className="compact-field"><span>Status</span><select value={alertStatus} onChange={(event) => setAlertStatus(event.target.value)}><option value="all">All statuses</option><option value="new">New</option><option value="acknowledged">Acknowledged</option><option value="dismissed">Dismissed</option></select></label><Button type="button" variant="outline" size="sm" disabled={!filteredAlerts.length} onClick={() => downloadRowsAsCsv("smart-alerts.csv", filteredAlerts.map(({ evidence, ...alert }) => ({ ...alert, evidence: evidence ? JSON.stringify(evidence) : "" })))}>Export filtered CSV</Button></div> : null}
      {item.href === "/smart-alerts" ? <div className="backend-notice" role="status"><CircleAlert aria-hidden="true" /><span>Severity and status filters and CSV export are available. Acknowledge and dismiss are unavailable until alert state has approved persistent storage; generated alerts remain new on refresh.</span></div> : null}
      {!dataset ? <EmptyState icon={Database} title="Choose a dataset to begin" description="Upload a CSV or Excel file to calculate this view from your data." action="Upload a dataset" /> : null}
      {isLoading ? <div className="loading-panel" aria-live="polite" /> : null}
      {error ? <p className="assistant-error" role="alert">{error.message}</p> : null}
      {data && !data.available ? <div className="backend-notice" role="status"><CircleAlert aria-hidden="true" /><span>{data.notes?.join(" ") || "This feature is unavailable for the uploaded dataset."}</span></div> : null}
      {data?.insights?.length ? <div className="insight-card"><CardHeader><CardTitle className="panel-title">Verified business insights</CardTitle><p className="panel-subtitle">Generated by the existing rule-based analytics engine.</p></CardHeader><CardContent><div className="ranked-list">{data.insights.map((insight) => <p className="insight-copy" key={insight}>{insight}</p>)}</div></CardContent></div> : null}
      {item.href === "/smart-alerts" && filteredAlerts.length ? <div className="info-grid alert-card-grid">{filteredAlerts.map((alert, index) => <Card className="panel-card" key={alert.id ?? `${alert.metric}-${index}`}><CardHeader><div className="alert-card-heading"><CardTitle className="panel-title">{alert.title}</CardTitle><div className="alert-badges"><Badge variant={alert.severity === "critical" ? "destructive" : "outline"}>{alert.severity}</Badge><Badge variant="secondary">{alert.status ?? "new"}</Badge></div></div><p className="panel-subtitle">{alert.description}</p></CardHeader><CardContent><p className="empty-copy">{alert.suggestion}</p><div className="alert-evidence"><span>{alert.scope ?? "Overall"}</span><span>{alert.comparison_period || "Comparison period unavailable"}</span></div>{alert.current_value != null || alert.previous_value != null ? <p className="alert-values">Current {alert.current_value?.toLocaleString("en-IN") ?? "—"} · Previous {alert.previous_value?.toLocaleString("en-IN") ?? "—"}{alert.pct_change != null ? ` · ${(alert.pct_change * 100).toFixed(1)}%` : ""}</p> : null}</CardContent></Card>)}</div> : null}
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
            <div className="table-wrap"><Table><TableHeader><TableRow>{fields.map((field) => <TableHead key={field}>{field.replaceAll("_", " ")}</TableHead>)}</TableRow></TableHeader><TableBody>{list.map((row, index) => <TableRow key={String(row[fields[0]]) + index}>{fields.map((field) => <TableCell key={field}>{String(row[field] ?? "—")}</TableCell>)}</TableRow>)}</TableBody></Table></div>
            {isCustomerTagging ? (
              <div className="segmentation-pagination" aria-label="Customer tag pages">
                <span>Showing {customerTotal ? customerOffset + 1 : 0}–{Math.min(customerOffset + list.length, customerTotal)} of {customerTotal.toLocaleString()} customers. Exports include the full result.</span>
                <div>
                  <Button type="button" variant="outline" size="sm" disabled={!hasPreviousCustomerPage} onClick={() => setCustomerOffset((offset) => Math.max(0, offset - 100))}>Previous</Button>
                  <Button type="button" variant="outline" size="sm" disabled={!hasNextCustomerPage} onClick={() => setCustomerOffset((offset) => offset + 100)}>Next</Button>
                </div>
              </div>
            ) : null}
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
  const reducedMotion = useReducedMotion();
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
      {result?.available ? <Card className="panel-card"><CardHeader className="panel-header"><div><CardTitle className="panel-title">Observed history and forecast</CardTitle><p className="panel-subtitle">Solid line is actual data; dashed lines show forecast and approximate interval bounds.</p></div><Button type="button" variant="outline" size="sm" onClick={() => downloadRowsAsCsv("forecast-results.csv", forecastExportRows)}>Download CSV</Button></CardHeader><CardContent><ChartContainer config={forecastChartConfig} className="forecast-chart"><LineChart accessibilityLayer data={forecastChartData} margin={{ left: 4, right: 12, top: 12, bottom: 0 }}><CartesianGrid vertical={false} strokeDasharray="3 3" /><XAxis dataKey="date" tickLine={false} axisLine={false} tickMargin={8} minTickGap={24} tickFormatter={(value) => new Date(String(value)).toLocaleDateString("en-IN", { month: "short", year: "2-digit" })} /><YAxis width={48} tickLine={false} axisLine={false} tickFormatter={(value) => new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 }).format(Number(value))} /><ChartTooltip content={<ChartTooltipContent indicator="line" formatter={(value) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(value))} />} /><Line type="monotone" dataKey="actual" stroke="var(--color-actual)" strokeWidth={2.5} dot={false} connectNulls={false} isAnimationActive={!reducedMotion} /><Line type="monotone" dataKey="forecast" stroke="var(--color-forecast)" strokeWidth={2.5} strokeDasharray="5 4" dot={false} connectNulls={false} isAnimationActive={!reducedMotion} /><Line type="monotone" dataKey="lower_bound" stroke="var(--color-lower_bound)" strokeWidth={1} strokeDasharray="2 4" dot={false} connectNulls={false} isAnimationActive={!reducedMotion} /><Line type="monotone" dataKey="upper_bound" stroke="var(--color-upper_bound)" strokeWidth={1} strokeDasharray="2 4" dot={false} connectNulls={false} isAnimationActive={!reducedMotion} /></LineChart></ChartContainer></CardContent></Card> : null}
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

  return <div className="page-stack"><PageHeading item={item} /><Card className="panel-card profile-settings-card"><CardHeader><CardTitle className="panel-title">Workspace preferences</CardTitle><p className="panel-subtitle">Preferences are saved in the existing user_preferences table.</p></CardHeader><CardContent>{error ? <p className="assistant-error" role="alert">{error.message}</p> : null}{isLoading ? <div className="loading-panel" aria-label="Loading preferences" /> : <form className="preferences-form" onSubmit={savePreferences}><label>Currency<select value={preferences.currency} onChange={(event) => setPreferenceOverrides((current) => ({ ...current, currency: event.target.value }))}><option value="INR">INR · Indian rupee</option><option value="USD">USD · US dollar</option><option value="EUR">EUR · Euro</option><option value="GBP">GBP · Pound sterling</option></select></label><label>Date format<select value={preferences.date_format} onChange={(event) => setPreferenceOverrides((current) => ({ ...current, date_format: event.target.value }))}><option>DD MMM YYYY</option><option>MM/DD/YYYY</option><option>YYYY-MM-DD</option></select></label><label>Default reporting period<select value={preferences.default_period} onChange={(event) => setPreferenceOverrides((current) => ({ ...current, default_period: event.target.value }))}><option value="7d">Last 7 days</option><option value="30d">Last 30 days</option><option value="90d">Last 90 days</option><option value="12m">Last 12 months</option></select></label><label className="compact-toggle"><input type="checkbox" checked={preferences.compact_mode} onChange={(event) => setPreferenceOverrides((current) => ({ ...current, compact_mode: event.target.checked }))} /> Use compact data tables</label><Button type="submit" disabled={saving}>{saving ? "Saving…" : "Save preferences"}</Button></form>}{message ? <p className={cn("upload-message", messageError && "upload-message-error")} role={messageError ? "alert" : "status"}>{message}</p> : null}</CardContent></Card></div>;
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
  if (item.href === "/datasets") return <DatasetPage item={item} />;
  if (item.href === "/activity") return <ActivityPage item={item} />;
  if (item.href === "/goals") return <GoalsPage item={item} />;
  if (item.href === "/owner-admin") return <OwnerAdminPage item={item} />;
  if (item.href === "/profile") return <ProfileSettingsPage item={item} />;
  if (item.href === "/account-settings" || item.href === "/security") return <AccountSecurityPage item={item} />;
  if (item.href === "/preferences") return <PreferencesPage item={item} />;
  if (item.href === "/data-connections") return <DataConnectionsPage item={item} />;
  if (item.href === "/performance-predictions") return <ScenarioPage item={item} />;
  if (item.group === "Business analytics") return <AnalyticsPage item={item} />;
  if (item.group === "AI intelligence") return <IntelligencePage item={item} />;
  if (item.group === "Predictive analytics") return <ForecastPage item={item} />;
  if (item.group === "Reports & exports") return <ReportsPage item={item} />;
  return <DataConnectionsPage item={item} />;
}
