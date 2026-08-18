import L from "leaflet";
import {
  downloadTile,
  getStorageInfo,
  saveTile,
  truncate as truncateStoredTiles,
} from "leaflet.offline";
import type { TileInfo } from "leaflet.offline";
import type { TileLayerOffline } from "leaflet.offline";

/**
 * Offline map-tile caching for the reserve map.
 *
 * The reserve is often surveyed with no signal, so the map should keep
 * showing camera stations and tiger ranges even without a connection.
 * `ReserveMap` renders an offline-capable tile layer (see
 * `OfflineTileLayer.tsx`) that reads tiles from IndexedDB first and only
 * falls back to the network when a tile hasn't been cached yet. This
 * module is the imperative half: downloading a bounded area of tiles
 * ahead of time ("save this view for offline use"), and reporting/
 * clearing what's already cached.
 *
 * Caveat worth keeping in mind: OpenStreetMap's tile usage policy
 * (https://operations.osmfoundation.org/policies/tiles/) discourages
 * bulk/automated tile scraping. `saveAreaForOffline` is meant for a
 * person caching the modest area they're about to patrol, not for
 * pre-downloading the whole reserve — see MAX_TILES_PER_SAVE below. For
 * heavier offline coverage, point `url` at a self-hosted tile server
 * instead.
 */

/** Hard cap on how many tiles a single "save this view" action will
 * fetch, regardless of the requested zoom range — keeps casual use well
 * within reasonable, non-bulk tile usage. */
export const MAX_TILES_PER_SAVE = 400;

/** How many zoom levels above the current one to include by default
 * when saving the current view (deeper zoom = sharper but many more
 * tiles: each extra level is ~4x the tiles of the one before it). */
export const DEFAULT_EXTRA_ZOOM_LEVELS = 2;

export interface SaveAreaProgress {
  loaded: number;
  total: number;
}

export interface SaveAreaResult {
  requested: number;
  saved: number;
  failed: number;
  /** True if the requested area/zoom range was clamped to stay under
   * MAX_TILES_PER_SAVE. */
  truncated: boolean;
}

export interface SaveAreaOptions {
  map: L.Map;
  layer: TileLayerOffline;
  bounds: L.LatLngBounds;
  minZoom: number;
  maxZoom: number;
  concurrency?: number;
  onProgress?: (progress: SaveAreaProgress) => void;
  signal?: AbortSignal;
}

/** Downloads and caches every tile covering `bounds` for each zoom level
 * in [minZoom, maxZoom], using the same tile URLs the map would request
 * live. Already-cached tiles are re-downloaded (cheap: browser HTTP
 * cache usually short-circuits it) so "save" also doubles as "refresh". */
export async function saveAreaForOffline({
  map,
  layer,
  bounds,
  minZoom,
  maxZoom,
  concurrency = 6,
  onProgress,
  signal,
}: SaveAreaOptions): Promise<SaveAreaResult> {
  let tiles: TileInfo[] = [];
  for (let zoom = minZoom; zoom <= maxZoom; zoom += 1) {
    const area = L.bounds(
      map.project(bounds.getNorthWest(), zoom),
      map.project(bounds.getSouthEast(), zoom),
    );
    tiles = tiles.concat(layer.getTileUrls(area, zoom));
  }

  const requested = tiles.length;
  const truncated = tiles.length > MAX_TILES_PER_SAVE;
  if (truncated) {
    tiles = tiles.slice(0, MAX_TILES_PER_SAVE);
  }

  const total = tiles.length;
  let loaded = 0;
  let saved = 0;
  let failed = 0;
  onProgress?.({ loaded: 0, total });

  const queue = [...tiles];

  async function worker() {
    for (;;) {
      if (signal?.aborted) return;
      const tile = queue.shift();
      if (!tile) return;
      try {
        const blob = await downloadTile(tile.url);
        await saveTile(tile, blob);
        saved += 1;
      } catch {
        failed += 1;
      } finally {
        loaded += 1;
        onProgress?.({ loaded, total });
      }
    }
  }

  await Promise.all(Array.from({ length: Math.min(concurrency, total) || 1 }, worker));

  return { requested, saved, failed, truncated };
}

export interface TileCacheStats {
  count: number;
  bytes: number;
}

/** Reads how many tiles (and roughly how many bytes) are already cached
 * for a given tile URL template. */
export async function getTileCacheStats(urlTemplate: string): Promise<TileCacheStats> {
  const stored = await getStorageInfo(urlTemplate);
  const bytes = stored.reduce((sum, tile) => sum + (tile.blob?.size ?? 0), 0);
  return { count: stored.length, bytes };
}

/** Clears every cached tile (all tile sources — this app only ever uses
 * one, so scoping further isn't necessary). */
export async function clearTileCache(): Promise<void> {
  await truncateStoredTiles();
}

export function formatBytes(bytes: number): string {
  if (bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** exponent;
  return `${exponent === 0 ? value : value.toFixed(1)} ${units[exponent]}`;
}
