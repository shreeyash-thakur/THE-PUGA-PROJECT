import type { BatchSummary, Camera, QuarantineItem, Sighting, Tiger } from "./types";

const KEY = "puga.apiBaseUrl";
export const DEFAULT_API_BASE = "http://localhost:8000";

/** Always resolves to a base URL — defaults to the local backend, never empty,
 * so the console always talks to a real service instead of silently falling
 * back to canned data. */
export function getApiBase(): string {
  if (typeof window === "undefined") return DEFAULT_API_BASE;
  return window.localStorage.getItem(KEY) || DEFAULT_API_BASE;
}

export function setApiBase(url: string) {
  if (typeof window === "undefined") return;
  if (url) window.localStorage.setItem(KEY, url);
  else window.localStorage.removeItem(KEY);
}

export interface Dataset {
  /** "live" once /api/health responds; "offline" when the local backend
   * couldn't be reached — the console shows an empty state with the error
   * rather than fabricated data. */
  source: "live" | "offline";
  baseUrl: string;
  error?: string | undefined;
  cameras: Camera[];
  tigers: Tiger[];
  sightings: Sighting[];
  quarantine: QuarantineItem[];
  lastBatch: BatchSummary | null;
}

const emptyDataset = (base: string, error?: string): Dataset => ({
  source: "offline",
  baseUrl: base,
  error,
  cameras: [],
  tigers: [],
  sightings: [],
  quarantine: [],
  lastBatch: null,
});

async function get<T>(base: string, path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${base}${path}`, signal ? { signal } : {});
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return (await res.json()) as T;
}

/** Fetches everything from the local PUGA FastAPI backend. If the backend is
 * unreachable, returns an empty "offline" dataset (with the error) instead
 * of demo data — nothing shown in the UI is ever fabricated. */
export async function loadDataset(base: string, signal?: AbortSignal): Promise<Dataset> {
  try {
    await get<{ status: string }>(base, "/api/health", signal);
    const [tigers, sightings, cameras, quarantine, lastBatch] = await Promise.all([
      get<Tiger[]>(base, "/api/tigers", signal),
      get<Sighting[]>(base, "/api/sightings", signal),
      get<Camera[]>(base, "/api/cameras", signal),
      get<QuarantineItem[]>(base, "/api/batch/quarantine", signal).catch(() => []),
      get<BatchSummary[]>(base, "/api/batch", signal)
        .then((batches) => batches[0] ?? null)
        .catch(() => null),
    ]);
    return {
      source: "live",
      baseUrl: base,
      cameras,
      tigers,
      sightings,
      quarantine,
      lastBatch,
    };
  } catch (err) {
    return emptyDataset(base, err instanceof Error ? err.message : "Backend unreachable");
  }
}

export async function runBatch(
  base: string,
  body: { folder_path: string; camera_id?: string; detection_threshold: number; recursive: boolean },
): Promise<BatchSummary> {
  const res = await fetch(`${base}/api/batch/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Batch failed: ${res.status} ${await res.text()}`);
  return (await res.json()) as BatchSummary;
}

export async function restoreQuarantined(base: string, id: number) {
  const res = await fetch(`${base}/api/batch/quarantine/${id}/restore`, { method: "POST" });
  if (!res.ok) throw new Error(`Restore failed: ${res.status}`);
  return res.json();
}
