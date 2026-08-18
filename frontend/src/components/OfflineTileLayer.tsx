import { useEffect, useRef } from "react";
import { useMap } from "react-leaflet";
import { tileLayerOffline } from "leaflet.offline";
import type { TileLayerOffline } from "leaflet.offline";
import type { TileLayerOptions } from "leaflet";

export interface OfflineTileLayerProps {
  url: string;
  attribution: string;
  minZoom?: number;
  maxZoom?: number;
  /** Fired once the underlying leaflet.offline layer is created and
   * attached to the map, so a parent (ReserveMap) can hand it to the
   * "save this view offline" controls without also owning the map
   * instance. */
  onLayerReady?: (layer: TileLayerOffline | null) => void;
}

/**
 * Drop-in replacement for react-leaflet's `<TileLayer>` that reads tiles
 * from IndexedDB first (via leaflet.offline) and only hits the network
 * for tiles that haven't been cached yet — see lib/puga/offline-tiles.ts
 * for how tiles get cached in the first place.
 *
 * leaflet.offline doesn't ship a react-leaflet binding, so this manages
 * the underlying Leaflet layer imperatively with useMap()/useEffect,
 * the same pattern react-leaflet itself uses internally for TileLayer.
 */
export function OfflineTileLayer({
  url,
  attribution,
  minZoom,
  maxZoom,
  onLayerReady,
}: OfflineTileLayerProps) {
  const map = useMap();
  const layerRef = useRef<TileLayerOffline | null>(null);

  useEffect(() => {
    const options: TileLayerOptions = { attribution };
    if (minZoom !== undefined) options.minZoom = minZoom;
    if (maxZoom !== undefined) options.maxZoom = maxZoom;

    const layer = tileLayerOffline(url, options);
    layer.addTo(map);
    layerRef.current = layer;
    onLayerReady?.(layer);

    return () => {
      map.removeLayer(layer);
      layerRef.current = null;
      onLayerReady?.(null);
    };
    // Re-create the layer only if the map instance or tile source
    // changes; attribution/zoom tweaks aren't expected at runtime here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, url]);

  return null;
}
