import { useEffect, useMemo, useRef, useState } from "react";
import { useMap } from "react-leaflet";
import L from "leaflet";
import type { TileLayerOffline } from "leaflet.offline";
import { CloudDownload, Trash2, Wifi, WifiOff } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { useOnlineStatus } from "@/hooks/use-online-status";
import {
  DEFAULT_EXTRA_ZOOM_LEVELS,
  clearTileCache,
  formatBytes,
  getTileCacheStats,
  saveAreaForOffline,
  type SaveAreaProgress,
} from "@/lib/puga/offline-tiles";

export interface MapOfflineControlsProps {
  layer: TileLayerOffline | null;
  urlTemplate: string;
  maxZoom: number;
}

/** Floating panel over the reserve map for caching tiles for offline
 * field use: shows whether the browser currently has a connection, how
 * many tiles are already cached, and lets a ranger cache the area
 * they're currently viewing before heading out. */
export function MapOfflineControls({ layer, urlTemplate, maxZoom }: MapOfflineControlsProps) {
  const map = useMap();
  const isOnline = useOnlineStatus();
  const containerRef = useRef<HTMLDivElement>(null);

  const [stats, setStats] = useState<{ count: number; bytes: number } | null>(null);
  const [saving, setSaving] = useState(false);
  const [progress, setProgress] = useState<SaveAreaProgress | null>(null);

  // Clicks/drags on this panel shouldn't pan or zoom the map underneath it.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    L.DomEvent.disableClickPropagation(el);
    L.DomEvent.disableScrollPropagation(el);
  }, []);

  const refreshStats = useMemo(
    () => async () => {
      try {
        setStats(await getTileCacheStats(urlTemplate));
      } catch {
        // IndexedDB unavailable (e.g. private browsing) — cache features
        // just stay disabled/unknown rather than breaking the map.
        setStats(null);
      }
    },
    [urlTemplate],
  );

  useEffect(() => {
    void refreshStats();
  }, [refreshStats]);

  async function handleSave() {
    if (!layer || saving) return;
    setSaving(true);
    setProgress(null);
    try {
      const zoom = map.getZoom();
      const result = await saveAreaForOffline({
        map,
        layer,
        bounds: map.getBounds(),
        minZoom: zoom,
        maxZoom: Math.min(zoom + DEFAULT_EXTRA_ZOOM_LEVELS, maxZoom),
        onProgress: setProgress,
      });

      if (result.saved === 0 && result.failed > 0) {
        toast.error("Couldn't cache this area — check your connection and try again.");
      } else {
        toast.success(
          result.failed > 0
            ? `Cached ${result.saved} tiles for offline use (${result.failed} failed).`
            : `Cached ${result.saved} tiles for offline use.`,
          result.truncated
            ? {
                description: `Zoomed area was large — capped at ${result.saved + result.failed} tiles.`,
              }
            : undefined,
        );
      }
      await refreshStats();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't save this area for offline use.");
    } finally {
      setSaving(false);
      setProgress(null);
    }
  }

  async function handleClear() {
    if (typeof window !== "undefined" && !window.confirm("Clear all cached offline map tiles?")) {
      return;
    }
    try {
      await clearTileCache();
      await refreshStats();
      toast.success("Cleared cached map tiles.");
    } catch {
      toast.error("Couldn't clear cached tiles.");
    }
  }

  return (
    <div
      ref={containerRef}
      className="absolute right-2 top-2 z-[1000] flex w-56 flex-col gap-2 rounded-lg border border-border bg-background/95 p-2.5 text-xs shadow-md backdrop-blur"
    >
      <div className="flex items-center justify-between gap-2">
        <Badge
          variant={isOnline ? "secondary" : "outline"}
          className="flex items-center gap-1 border-warning/40 text-[11px]"
        >
          {isOnline ? <Wifi className="size-3" /> : <WifiOff className="size-3 text-warning" />}
          {isOnline ? "Online" : "Offline — using cached tiles"}
        </Badge>
      </div>

      <div className="text-muted-foreground">
        {stats
          ? `${stats.count} tile${stats.count === 1 ? "" : "s"} cached (${formatBytes(stats.bytes)})`
          : "Offline tile cache unavailable"}
      </div>

      {saving && progress ? (
        <div className="space-y-1">
          <Progress value={progress.total ? (progress.loaded / progress.total) * 100 : 0} />
          <div className="text-[11px] text-muted-foreground">
            Saving tiles… {progress.loaded}/{progress.total}
          </div>
        </div>
      ) : null}

      <div className="flex gap-2">
        <Button
          type="button"
          size="sm"
          variant="secondary"
          className="h-7 flex-1 gap-1 px-2 text-[11px]"
          disabled={!layer || saving || !isOnline}
          onClick={handleSave}
          title={!isOnline ? "Connect once to cache this view, then it works offline" : undefined}
        >
          <CloudDownload className="size-3" />
          {saving ? "Saving…" : "Save this view"}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-7 gap-1 px-2 text-[11px]"
          disabled={!stats || stats.count === 0}
          onClick={handleClear}
        >
          <Trash2 className="size-3" />
        </Button>
      </div>
    </div>
  );
}
