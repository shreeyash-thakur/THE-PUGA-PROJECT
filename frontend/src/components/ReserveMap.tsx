import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { CircleMarker, MapContainer, Polygon, Popup, TileLayer, Tooltip } from "react-leaflet";
import type { Camera } from "@/lib/puga/types";
import type { Occupancy } from "@/lib/puga/occupancy";

// Avoid the default marker-icon 404s; we only draw vector markers.
L.Marker.prototype.options.icon = L.divIcon({ className: "hidden" });

const RANGE_COLORS = [
  "#f0a03c",
  "#4fbf8b",
  "#63a9e6",
  "#e97a6a",
  "#c79ae8",
  "#e8c95a",
  "#6fd4c5",
  "#eb8fc0",
];

const ZONE_COLOR: Record<Camera["zone"], string> = {
  core: "#4fbf8b",
  buffer: "#e8c95a",
  "village-adjacent": "#e97a6a",
};

export interface ReserveMapProps {
  cameras: Camera[];
  ranges: Occupancy[];
  center?: [number, number];
  zoom?: number;
  height?: number;
}

export default function ReserveMap({
  cameras,
  ranges,
  center = [21.702, 79.283],
  zoom = 11,
  height = 520,
}: ReserveMapProps) {
  return (
    <MapContainer
      center={center}
      zoom={zoom}
      style={{ height, width: "100%", borderRadius: "0.75rem" }}
      scrollWheelZoom
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      {ranges.map((r, i) => {
        const color = RANGE_COLORS[i % RANGE_COLORS.length]!;
        return (
          <span key={r.tiger_id}>
            {r.hull.length >= 3 ? (
              <Polygon
                positions={r.hull.map((p) => [p.lat, p.lng] as [number, number])}
                pathOptions={{ color, fillColor: color, fillOpacity: 0.16, weight: 2 }}
              >
                <Tooltip sticky>
                  {r.tiger_id} — {r.areaKm2.toFixed(1)} km² MCP, {r.sightings} captures
                </Tooltip>
              </Polygon>
            ) : null}
            {r.centroid ? (
              <CircleMarker
                center={[r.centroid.lat, r.centroid.lng]}
                radius={7}
                pathOptions={{ color, fillColor: color, fillOpacity: 0.95, weight: 2 }}
              >
                <Popup>
                  <strong>{r.tiger_id}</strong>
                  <br />
                  Centroid {r.centroid.lat.toFixed(4)}, {r.centroid.lng.toFixed(4)}
                  <br />
                  {r.stations.length} stations · {r.areaKm2.toFixed(1)} km²
                </Popup>
              </CircleMarker>
            ) : null}
          </span>
        );
      })}

      {cameras.map((c) => (
        <CircleMarker
          key={c.camera_id}
          center={[c.latitude, c.longitude]}
          radius={4}
          pathOptions={{
            color: ZONE_COLOR[c.zone],
            fillColor: ZONE_COLOR[c.zone],
            fillOpacity: 0.9,
            weight: 1,
          }}
        >
          <Popup>
            <strong>{c.camera_id}</strong>
            <br />
            {c.name} · {c.zone}
            <br />
            Installed {c.installed_at}
          </Popup>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}
