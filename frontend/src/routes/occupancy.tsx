import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Download, Layers } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { MapPanel } from "@/components/MapPanel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { downloadCsv, downloadJson, rangesToGeoJson } from "@/lib/puga/export";
import { computeOccupancy, overlapPairs } from "@/lib/puga/occupancy";
import { useDataset } from "@/lib/puga/use-dataset";

export const Route = createFileRoute("/occupancy")({
  head: () => ({
    meta: [
      { title: "Occupancy map — PUGA tiger reserve intelligence" },
      {
        name: "description",
        content:
          "Tiger-wise area occupancy regenerated every run: home ranges, activity centroids, occupied area and territorial overlap on a reserve map.",
      },
      { property: "og:title", content: "Occupancy map — PUGA" },
      {
        property: "og:description",
        content: "Home ranges, centroids and territorial overlap, exportable as CSV and GeoJSON.",
      },
    ],
  }),
  component: OccupancyPage,
});

function OccupancyPage() {
  const { data } = useDataset();
  const cameras = data?.cameras ?? [];
  const sightings = data?.sightings ?? [];
  const [selected, setSelected] = useState<string[]>([]);

  const ranges = useMemo(
    () => (data?.tigers ?? []).map((t) => computeOccupancy(t.tiger_id, sightings, cameras)),
    [data, sightings, cameras],
  );
  const visible = selected.length ? ranges.filter((r) => selected.includes(r.tiger_id)) : ranges;
  const overlaps = useMemo(() => overlapPairs(ranges), [ranges]);

  function toggle(id: string) {
    setSelected((prev) => (prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]));
  }

  return (
    <AppShell
      title="Area occupancy"
      subtitle="Regenerated on every processing run from the individual database."
      actions={
        <div className="flex gap-2">
          <Button
            variant="secondary"
            onClick={() =>
              downloadCsv(
                "puga-occupancy.csv",
                ranges.map((r) => ({
                  tiger_id: r.tiger_id,
                  captures: r.sightings,
                  stations: r.stations.join(" "),
                  area_km2: r.areaKm2.toFixed(2),
                  max_span_km: r.maxSpanKm.toFixed(2),
                  centroid_lat: r.centroid?.lat.toFixed(5) ?? "",
                  centroid_lng: r.centroid?.lng.toFixed(5) ?? "",
                  core: r.zones["core"] ?? 0,
                  buffer: r.zones["buffer"] ?? 0,
                  village_adjacent: r.zones["village-adjacent"] ?? 0,
                })),
              )
            }
          >
            <Download className="mr-2 size-4" /> CSV
          </Button>
          <Button onClick={() => downloadJson("puga-home-ranges.geojson", rangesToGeoJson(ranges))}>
            <Layers className="mr-2 size-4" /> GeoJSON
          </Button>
        </div>
      }
    >
      <div className="mb-4 flex flex-wrap gap-2">
        {ranges.map((r) => (
          <button
            key={r.tiger_id}
            onClick={() => toggle(r.tiger_id)}
            className={`rounded-full border px-3 py-1 text-xs transition-colors ${
              selected.includes(r.tiger_id)
                ? "border-primary bg-primary/15 text-primary"
                : "border-border text-muted-foreground hover:text-foreground"
            }`}
          >
            {r.tiger_id}
          </button>
        ))}
        {selected.length ? (
          <button
            onClick={() => setSelected([])}
            className="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground"
          >
            Show all
          </button>
        ) : null}
      </div>

      <Card className="panel">
        <CardContent className="pt-6">
          <MapPanel cameras={cameras} ranges={visible} height={560} />
          <div className="mt-3 flex flex-wrap gap-4 text-xs text-muted-foreground">
            <Legend color="#4fbf8b" label="Core station" />
            <Legend color="#e8c95a" label="Buffer station" />
            <Legend color="#e97a6a" label="Village-adjacent station" />
            <span>Filled polygons are per-individual minimum convex polygons.</span>
          </div>
        </CardContent>
      </Card>

      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <Card className="panel">
          <CardHeader>
            <CardTitle>Per-individual occupancy</CardTitle>
            <CardDescription>Locations, centroid and estimated occupied area.</CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Individual</TableHead>
                  <TableHead>Stations</TableHead>
                  <TableHead>Area</TableHead>
                  <TableHead>Centroid</TableHead>
                  <TableHead>Zone mix</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {ranges.map((r) => (
                  <TableRow key={r.tiger_id}>
                    <TableCell className="font-mono text-xs">{r.tiger_id}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {r.stations.join(", ") || "—"}
                    </TableCell>
                    <TableCell>{r.areaKm2.toFixed(1)} km²</TableCell>
                    <TableCell className="font-mono text-xs">
                      {r.centroid
                        ? `${r.centroid.lat.toFixed(3)}, ${r.centroid.lng.toFixed(3)}`
                        : "—"}
                    </TableCell>
                    <TableCell className="text-xs">
                      C {r.zones["core"] ?? 0} · B {r.zones["buffer"] ?? 0} · V{" "}
                      {r.zones["village-adjacent"] ?? 0}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card className="panel">
          <CardHeader>
            <CardTitle>Territorial overlap</CardTitle>
            <CardDescription>
              Shared stations between individuals — itself a management signal.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {overlaps.length === 0 ? (
              <p className="text-sm text-muted-foreground">No shared stations this cycle.</p>
            ) : (
              overlaps.map((o) => (
                <div
                  key={`${o.a}-${o.b}`}
                  className="flex items-center justify-between rounded-md border border-border p-3"
                >
                  <div>
                    <p className="font-mono text-sm">
                      {o.a} ↔ {o.b}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {o.sharedStations.join(", ")}
                    </p>
                  </div>
                  <Badge variant={o.sharedStations.length > 2 ? "destructive" : "secondary"}>
                    {o.sharedStations.length} shared · {o.centroidKm} km apart
                  </Badge>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-2">
      <span className="size-2.5 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </span>
  );
}
