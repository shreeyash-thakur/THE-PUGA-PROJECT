import type { Camera, Sighting } from "./types";

export interface LatLng {
  lat: number;
  lng: number;
}

const KM_PER_DEG_LAT = 110.574;
const kmPerDegLng = (lat: number) => 111.32 * Math.cos((lat * Math.PI) / 180);

export function haversineKm(a: LatLng, b: LatLng): number {
  const R = 6371;
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLng = ((b.lng - a.lng) * Math.PI) / 180;
  const la1 = (a.lat * Math.PI) / 180;
  const la2 = (b.lat * Math.PI) / 180;
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

export function centroid(points: LatLng[]): LatLng | null {
  if (points.length === 0) return null;
  const lat = points.reduce((s, p) => s + p.lat, 0) / points.length;
  const lng = points.reduce((s, p) => s + p.lng, 0) / points.length;
  return { lat, lng };
}

/** Andrew's monotone chain convex hull (minimum convex polygon). */
export function convexHull(points: LatLng[]): LatLng[] {
  const pts = [...points].sort((a, b) => a.lng - b.lng || a.lat - b.lat);
  if (pts.length < 3) return pts;
  const cross = (o: LatLng, a: LatLng, b: LatLng) =>
    (a.lng - o.lng) * (b.lat - o.lat) - (a.lat - o.lat) * (b.lng - o.lng);
  const lower: LatLng[] = [];
  for (const p of pts) {
    while (lower.length >= 2 && cross(lower[lower.length - 2]!, lower[lower.length - 1]!, p) <= 0)
      lower.pop();
    lower.push(p);
  }
  const upper: LatLng[] = [];
  for (let i = pts.length - 1; i >= 0; i--) {
    const p = pts[i]!;
    while (upper.length >= 2 && cross(upper[upper.length - 2]!, upper[upper.length - 1]!, p) <= 0)
      upper.pop();
    upper.push(p);
  }
  lower.pop();
  upper.pop();
  return lower.concat(upper);
}

/** Planar shoelace area of a lat/lng polygon, in square kilometres. */
export function polygonAreaKm2(poly: LatLng[]): number {
  if (poly.length < 3) return 0;
  const lat0 = centroid(poly)!.lat;
  const xy = poly.map((p) => ({ x: p.lng * kmPerDegLng(lat0), y: p.lat * KM_PER_DEG_LAT }));
  let sum = 0;
  for (let i = 0; i < xy.length; i++) {
    const a = xy[i]!;
    const b = xy[(i + 1) % xy.length]!;
    sum += a.x * b.y - b.x * a.y;
  }
  return Math.abs(sum) / 2;
}

export interface Occupancy {
  tiger_id: string;
  sightings: number;
  stations: string[];
  points: LatLng[];
  hull: LatLng[];
  centroid: LatLng | null;
  areaKm2: number;
  maxSpanKm: number;
  zones: Record<string, number>;
  firstSeen: string | null;
  lastSeen: string | null;
}

export function computeOccupancy(
  tigerId: string,
  sightings: Sighting[],
  cameras: Camera[],
): Occupancy {
  const zoneOf = new Map(cameras.map((c) => [c.camera_id, c.zone]));
  const own = sightings
    .filter((s) => s.tiger_id === tigerId && s.latitude != null && s.longitude != null)
    .sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  const points = own.map((s) => ({ lat: s.latitude!, lng: s.longitude! }));
  const hull = convexHull(points);
  const zones: Record<string, number> = {};
  for (const s of own) {
    const z = (s.camera_id && zoneOf.get(s.camera_id)) || "unknown";
    zones[z] = (zones[z] ?? 0) + 1;
  }
  let maxSpanKm = 0;
  for (let i = 0; i < points.length; i++)
    for (let j = i + 1; j < points.length; j++)
      maxSpanKm = Math.max(maxSpanKm, haversineKm(points[i]!, points[j]!));

  return {
    tiger_id: tigerId,
    sightings: own.length,
    stations: [...new Set(own.map((s) => s.camera_id).filter(Boolean) as string[])],
    points,
    hull,
    centroid: centroid(points),
    areaKm2: polygonAreaKm2(hull),
    maxSpanKm,
    zones,
    firstSeen: own[0]?.timestamp ?? null,
    lastSeen: own[own.length - 1]?.timestamp ?? null,
  };
}

export function overlapPairs(occ: Occupancy[]) {
  const out: Array<{ a: string; b: string; sharedStations: string[]; centroidKm: number }> = [];
  for (let i = 0; i < occ.length; i++) {
    for (let j = i + 1; j < occ.length; j++) {
      const A = occ[i]!;
      const B = occ[j]!;
      const shared = A.stations.filter((s) => B.stations.includes(s));
      if (shared.length === 0 || !A.centroid || !B.centroid) continue;
      out.push({
        a: A.tiger_id,
        b: B.tiger_id,
        sharedStations: shared,
        centroidKm: +haversineKm(A.centroid, B.centroid).toFixed(2),
      });
    }
  }
  return out.sort((x, y) => y.sharedStations.length - x.sharedStations.length);
}
