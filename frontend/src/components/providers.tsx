"use client";

import { createContext, useCallback, useContext, useMemo, useState, useSyncExternalStore, type ReactNode } from "react";
import useSWR from "swr";
import { AnimationPreferenceProvider } from "@/lib/animation-preference";

export type ActiveDataset = {
  id: string;
  filename: string;
  uploadedAt: string;
  rows: number;
  columns: string[];
  preview: Record<string, string | number | null>[];
  mapping: Record<string, string | null>;
  profile: Record<string, string[]>;
  quality: { missing_cells: number; columns_with_missing_values: number; duplicate_rows: number };
};

export type DatasetSummary = {
  id: string;
  filename: string;
  file_type: string;
  rows: number;
  size_bytes: number;
  created_at: string;
  validation_status: string;
};

export type SessionData = {
  user: {
    id: number;
    email: string;
    full_name: string;
    phone: string | null;
    account_status: string;
  };
  role: "owner_admin" | "user";
};

type ApiError = Error & { status?: number };

const REQUEST_TIMEOUT_MS = 20000;

async function fetchJson<T>(url: string): Promise<T> {
  // A backend that is still booting (or unreachable) must never leave the UI
  // on the session screen forever. Abort and surface a retryable error instead.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(url, { cache: "no-store", signal: controller.signal });
  } catch (reason) {
    const error = new Error(
      reason instanceof DOMException && reason.name === "AbortError"
        ? "The analytics service took too long to respond. Check that the Python API is running, then retry."
        : "The analytics service could not be reached. Check your connection and that the Python API is running, then retry.",
    ) as ApiError;
    error.status = 0;
    throw error;
  } finally {
    clearTimeout(timer);
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.detail || "Could not load workspace data.") as ApiError;
    error.status = response.status;
    throw error;
  }
  return payload as T;
}

export { fetchJson };

type DatasetContextValue = {
  dataset: ActiveDataset | null;
  datasets: DatasetSummary[];
  datasetsLoading: boolean;
  setDataset: (dataset: ActiveDataset | null) => void;
  resetDatasetSelection: () => void;
  refreshDatasets: () => Promise<unknown>;
};

type SessionContextValue = {
  session: SessionData | null;
  sessionLoading: boolean;
  sessionError: ApiError | undefined;
  retrySession: () => Promise<unknown>;
};

const DatasetContext = createContext<DatasetContextValue | null>(null);
const SessionContext = createContext<SessionContextValue | null>(null);

const ACTIVE_DATASET_PREFIX = "retailmind_active_dataset";

function storageKeyFor(session: SessionData | undefined): string | null {
  return session ? `${ACTIVE_DATASET_PREFIX}:${session.user.id}` : null;
}

// The persisted dataset id is read from localStorage through an external store
// so it is never copied into React state inside an effect (which would trigger
// a cascading render on boot).
const activeDatasetListeners = new Set<() => void>();

function subscribeActiveDataset(listener: () => void): () => void {
  activeDatasetListeners.add(listener);
  const onStorage = (event: StorageEvent) => {
    if (!event.key || event.key.startsWith(ACTIVE_DATASET_PREFIX)) listener();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    activeDatasetListeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

function notifyActiveDatasetChange(): void {
  for (const listener of activeDatasetListeners) listener();
}

function readPersistedDatasetId(storageKey: string | null): string | null {
  if (!storageKey) return null;
  try {
    return window.localStorage.getItem(storageKey);
  } catch {
    return null;
  }
}

export function AppProviders({ children }: { children: ReactNode }) {
  const { data: session, error: sessionError, isLoading: sessionLoading, mutate: retrySession } = useSWR<SessionData>(
    "/api/retailmind/auth/session",
    fetchJson,
    {
      revalidateOnFocus: true,
      dedupingInterval: 60000,
      // One short retry smooths over a cold backend without masking a real outage.
      shouldRetryOnError: true,
      errorRetryCount: 1,
      errorRetryInterval: 1500,
    },
  );
  const { data: datasetIndex, isLoading: datasetsLoading, mutate: refreshDatasets } = useSWR<{ datasets: DatasetSummary[] }>(
    session ? "/api/retailmind/datasets" : null,
    fetchJson,
    { revalidateOnFocus: true, dedupingInterval: 30000, keepPreviousData: true, shouldRetryOnError: false },
  );
  const [datasetOverride, setDatasetOverride] = useState<ActiveDataset | null | undefined>(undefined);
  const storageKey = storageKeyFor(session);

  // Restore the dataset the user last chose. Keyed per user so one account can
  // never inherit another account's selection.
  const persistedId = useSyncExternalStore(
    subscribeActiveDataset,
    () => readPersistedDatasetId(storageKey),
    () => null,
  );

  // A stored id is trusted only while it still appears in this user's list, so
  // a deleted or foreign id silently falls back to the newest dataset.
  const validPersistedId = persistedId && datasetIndex?.datasets.some((entry) => entry.id === persistedId)
    ? persistedId
    : null;

  const defaultDatasetId = datasetOverride === undefined
    ? (validPersistedId ?? datasetIndex?.datasets[0]?.id)
    : undefined;

  const { data: savedDataset } = useSWR<{
    dataset_id: string;
    filename: string;
    created_at?: string | null;
    row_count: number;
    columns: string[];
    preview: ActiveDataset["preview"];
    mapping: ActiveDataset["mapping"];
    profile: ActiveDataset["profile"];
    quality: ActiveDataset["quality"];
  }>(
    session && defaultDatasetId ? `/api/retailmind/datasets/${encodeURIComponent(defaultDatasetId)}` : null,
    fetchJson,
    { revalidateOnFocus: false, dedupingInterval: 30000, keepPreviousData: true, shouldRetryOnError: false },
  );

  const selectDataset = useCallback((next: ActiveDataset | null) => {
    setDatasetOverride(next);
    if (typeof window === "undefined" || !storageKey) return;
    try {
      if (next) window.localStorage.setItem(storageKey, next.id);
      else window.localStorage.removeItem(storageKey);
    } catch {
      /* The selection still applies to this session. */
    }
    notifyActiveDatasetChange();
  }, [storageKey]);

  const resetDatasetSelection = useCallback(() => {
    setDatasetOverride(undefined);
    if (typeof window === "undefined" || !storageKey) return;
    try {
      window.localStorage.removeItem(storageKey);
    } catch {
      /* The default dataset still applies. */
    }
    notifyActiveDatasetChange();
  }, [storageKey]);

  const datasetValue = useMemo(() => {
    const activeDataset: ActiveDataset | null = (sessionError as ApiError | undefined)?.status === 401
      ? null
      : datasetOverride === undefined
        ? savedDataset
          ? {
              id: savedDataset.dataset_id,
              filename: savedDataset.filename,
              uploadedAt: savedDataset.created_at ?? "",
              rows: savedDataset.row_count,
              columns: savedDataset.columns,
              preview: savedDataset.preview,
              mapping: savedDataset.mapping,
              profile: savedDataset.profile,
              quality: savedDataset.quality,
            }
          : null
        : datasetOverride;
    return {
      dataset: activeDataset,
      datasets: datasetIndex?.datasets ?? [],
      datasetsLoading,
      setDataset: selectDataset,
      resetDatasetSelection,
      refreshDatasets,
    };
  }, [datasetIndex?.datasets, datasetsLoading, datasetOverride, refreshDatasets, resetDatasetSelection, savedDataset, selectDataset, sessionError]);
  const sessionValue = useMemo(() => ({
    session: session ?? null,
    sessionLoading,
    sessionError: sessionError as ApiError | undefined,
    retrySession: () => retrySession(),
  }), [session, sessionLoading, sessionError, retrySession]);

  return (
    <AnimationPreferenceProvider>
      <SessionContext.Provider value={sessionValue}>
        <DatasetContext.Provider value={datasetValue}>{children}</DatasetContext.Provider>
      </SessionContext.Provider>
    </AnimationPreferenceProvider>
  );
}

export function useDataset() {
  const context = useContext(DatasetContext);
  if (!context) throw new Error("useDataset must be used inside AppProviders.");
  return context;
}

export function useSession() {
  const context = useContext(SessionContext);
  if (!context) throw new Error("useSession must be used inside AppProviders.");
  return context;
}
