export function toCsv(rows: Array<Record<string, string | number>>): string {
  if (rows.length === 0) return "";
  const headers = Object.keys(rows[0]!);
  const esc = (v: string | number) => {
    const s = String(v ?? "");
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [headers.join(","), ...rows.map((r) => headers.map((h) => esc(r[h] ?? "")).join(","))].join(
    "\n",
  );
}

export function downloadText(filename: string, text: string, mime = "text/plain") {
  if (typeof window === "undefined") return;
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function downloadCsv(filename: string, rows: Array<Record<string, string | number>>) {
  downloadText(filename, toCsv(rows), "text/csv");
}

export function downloadJson(filename: string, data: unknown) {
  downloadText(filename, JSON.stringify(data, null, 2), "application/json");
}

/** GeoJSON export of home ranges for forest-department GIS tools. */
export function rangesToGeoJson(
  ranges: Array<{
    tiger_id: string;
    hull: Array<{ lat: number; lng: number }>;
    centroid: { lat: number; lng: number } | null;
    areaKm2: number;
    sightings: number;
    stations: string[];
  }>,
) {
  return {
    type: "FeatureCollection",
    features: ranges.flatMap((r) => {
      const feats: unknown[] = [];
      if (r.hull.length >= 3) {
        feats.push({
          type: "Feature",
          properties: {
            tiger_id: r.tiger_id,
            area_km2: +r.areaKm2.toFixed(2),
            captures: r.sightings,
            stations: r.stations.join(" "),
          },
          geometry: {
            type: "Polygon",
            coordinates: [[...r.hull, r.hull[0]!].map((p) => [p.lng, p.lat])],
          },
        });
      }
      if (r.centroid) {
        feats.push({
          type: "Feature",
          properties: { tiger_id: r.tiger_id, kind: "centroid" },
          geometry: { type: "Point", coordinates: [r.centroid.lng, r.centroid.lat] },
        });
      }
      return feats;
    }),
  };
}
