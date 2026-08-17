import { computeOccupancy, haversineKm } from "./occupancy";
import type { Camera, Sighting } from "./types";

export type AlertSeverity = "critical" | "warning" | "info";

export interface Alert {
  id: string;
  tiger_id: string;
  type:
    | "centroid-shift"
    | "new-station"
    | "buffer-movement"
    | "prolonged-absence"
    | "effort-artefact";
  severity: AlertSeverity;
  title: string;
  what_changed: string;
  evidence: string[];
  confidence: number;
  confidence_label: "high" | "medium" | "low";
  suppressed?: boolean;
}

export interface AlertConfig {
  /** Centroid shift threshold inside the core, in km (≈15–20 km² of displaced range). */
  coreShiftKm: number;
  /** Centroid shift threshold in the buffer, in km. */
  bufferShiftKm: number;
  /** Days without a capture before an individual counts as absent. */
  absenceDays: number;
  /** Length of the current run window, in days. */
  runWindowDays: number;
}

export const DEFAULT_ALERT_CONFIG: AlertConfig = {
  coreShiftKm: 4.5,
  bufferShiftKm: 5,
  absenceDays: 120,
  runWindowDays: 90,
};

function label(c: number): Alert["confidence_label"] {
  return c >= 0.8 ? "high" : c >= 0.55 ? "medium" : "low";
}

export function generateAlerts(
  sightings: Sighting[],
  cameras: Camera[],
  config: AlertConfig = DEFAULT_ALERT_CONFIG,
): Alert[] {
  if (sightings.length === 0) return [];
  const camById = new Map(cameras.map((c) => [c.camera_id, c]));
  const latest = sightings.reduce(
    (m, s) => (s.timestamp > m ? s.timestamp : m),
    sightings[0]!.timestamp,
  );
  const latestMs = new Date(latest).getTime();
  const runStart = latestMs - config.runWindowDays * 86400000;

  const current = sightings.filter((s) => new Date(s.timestamp).getTime() >= runStart);
  const history = sightings.filter((s) => new Date(s.timestamp).getTime() < runStart);
  const historyEndMs = history.length
    ? Math.max(...history.map((s) => new Date(s.timestamp).getTime()))
    : runStart;

  const tigerIds = [...new Set(sightings.map((s) => s.tiger_id))];
  const alerts: Alert[] = [];

  for (const id of tigerIds) {
    const hist = computeOccupancy(id, history, cameras);
    const cur = computeOccupancy(id, current, cameras);
    const histStations = new Set(hist.stations);

    // 4. Prolonged absence
    if (cur.sightings === 0 && hist.lastSeen) {
      const days = Math.round((latestMs - new Date(hist.lastSeen).getTime()) / 86400000);
      if (days >= config.absenceDays) {
        const conf = Math.min(0.95, 0.5 + hist.sightings / 40);
        alerts.push({
          id: `${id}-absence`,
          tiger_id: id,
          type: "prolonged-absence",
          severity: "critical",
          title: `${id} not recorded for ${days} days`,
          what_changed: `A previously regular individual (${hist.sightings} captures across ${hist.stations.length} stations) has no capture in the current run.`,
          evidence: [
            `Last capture ${new Date(hist.lastSeen).toISOString().slice(0, 10)} at ${hist.stations.slice(-1)[0] ?? "unknown station"}`,
            `${hist.stations.filter((s) => current.some((c) => c.camera_id === s)).length} of its ${hist.stations.length} historical stations were active this run — absence is not an effort gap`,
          ],
          confidence: +conf.toFixed(2),
          confidence_label: label(conf),
        });
      }
      continue;
    }
    if (cur.sightings === 0) continue;

    // 1. Centroid shift
    if (hist.centroid && cur.centroid) {
      const shift = haversineKm(hist.centroid, cur.centroid);
      const inBuffer =
        (cur.zones["buffer"] ?? 0) + (cur.zones["village-adjacent"] ?? 0) >
        (cur.zones["core"] ?? 0);
      const threshold = inBuffer ? config.bufferShiftKm : config.coreShiftKm;
      if (shift >= threshold) {
        const conf = Math.min(0.95, 0.35 + Math.min(cur.sightings, 12) / 20);
        alerts.push({
          id: `${id}-centroid`,
          tiger_id: id,
          type: "centroid-shift",
          severity: shift >= threshold * 1.6 ? "critical" : "warning",
          title: `${id} range centroid shifted ${shift.toFixed(1)} km`,
          what_changed: `Activity centre moved ${shift.toFixed(1)} km (${inBuffer ? "buffer" : "core"} threshold ${threshold} km); occupied area changed from ${hist.areaKm2.toFixed(1)} km² to ${cur.areaKm2.toFixed(1)} km².`,
          evidence: [
            `Historic centroid ${hist.centroid.lat.toFixed(4)}, ${hist.centroid.lng.toFixed(4)} (${hist.sightings} captures)`,
            `Current centroid ${cur.centroid.lat.toFixed(4)}, ${cur.centroid.lng.toFixed(4)} (${cur.sightings} captures)`,
            `Stations this run: ${cur.stations.join(", ")}`,
          ],
          confidence: +conf.toFixed(2),
          confidence_label: label(conf),
        });
      }
    }

    // 2. First capture at a never-used station (with survey-effort check)
    const newStations = cur.stations.filter((s) => !histStations.has(s));
    for (const st of newStations) {
      const cam = camById.get(st);
      const installedMs = cam ? new Date(cam.installed_at).getTime() : 0;
      const isNewCamera = installedMs > historyEndMs;
      const conf = isNewCamera ? 0.3 : Math.min(0.92, 0.55 + cur.sightings / 30);
      alerts.push({
        id: `${id}-new-${st}`,
        tiger_id: id,
        type: isNewCamera ? "effort-artefact" : "new-station",
        severity: isNewCamera ? "info" : "warning",
        title: isNewCamera
          ? `${id} at new camera ${st} — survey-effort artefact`
          : `${id} first capture at ${st}`,
        what_changed: isNewCamera
          ? `Station ${st} (${cam?.name}) was installed ${cam?.installed_at}, after the previous cycle. The "new" detection is explained by new survey effort, not by movement.`
          : `Individual recorded for the first time at ${st} (${cam?.name ?? "unknown"}, ${cam?.zone ?? "?"} zone).`,
        evidence: [
          `Station operational since ${cam?.installed_at ?? "unknown"}`,
          `${current.filter((s) => s.tiger_id === id && s.camera_id === st).length} captures this run at this station`,
          `Not present in ${hist.sightings} historical captures`,
        ],
        confidence: +conf.toFixed(2),
        confidence_label: label(conf),
        suppressed: isNewCamera,
      });
    }

    // 3. Movement into buffer / village-adjacent stations
    const risky = cur.stations
      .map((s) => camById.get(s))
      .filter((c): c is Camera => !!c && c.zone !== "core");
    const newRisky = risky.filter((c) => !histStations.has(c.camera_id));
    if (newRisky.length > 0) {
      const village = newRisky.filter((c) => c.zone === "village-adjacent");
      const conf = Math.min(0.94, 0.5 + newRisky.length / 6);
      alerts.push({
        id: `${id}-buffer`,
        tiger_id: id,
        type: "buffer-movement",
        severity: village.length > 0 ? "critical" : "warning",
        title:
          village.length > 0
            ? `${id} moving toward village-adjacent stations`
            : `${id} entering buffer stations`,
        what_changed: `New captures at ${newRisky.map((c) => `${c.camera_id} (${c.zone})`).join(", ")} — a direction of travel out of the core.`,
        evidence: [
          `${cur.zones["buffer"] ?? 0} buffer and ${cur.zones["village-adjacent"] ?? 0} village-adjacent captures this run`,
          `Historic zone mix: core ${hist.zones["core"] ?? 0}, buffer ${hist.zones["buffer"] ?? 0}, village ${hist.zones["village-adjacent"] ?? 0}`,
          ...village.map((c) => `Village-adjacent capture at ${c.name}`),
        ],
        confidence: +conf.toFixed(2),
        confidence_label: label(conf),
      });
    }
  }

  const order: Record<AlertSeverity, number> = { critical: 0, warning: 1, info: 2 };
  return alerts.sort(
    (a, b) => order[a.severity] - order[b.severity] || b.confidence - a.confidence,
  );
}
