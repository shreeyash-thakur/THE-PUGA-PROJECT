import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowLeft, Check, Download, Flag } from "lucide-react";
import { toast } from "sonner";
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
import { generateAlerts } from "@/lib/puga/alerts";
import { downloadCsv } from "@/lib/puga/export";
import { computeOccupancy } from "@/lib/puga/occupancy";
import { useDataset } from "@/lib/puga/use-dataset";

export const Route = createFileRoute("/tigers/$tigerId")({
  head: ({ params }) => ({
    meta: [
      { title: `${params.tigerId} — individual profile | PUGA` },
      {
        name: "description",
        content: `Capture history, station list, home range estimate and movement alerts for individual ${params.tigerId} in Pench Tiger Reserve.`,
      },
      { property: "og:title", content: `${params.tigerId} — individual profile | PUGA` },
      {
        property: "og:description",
        content: `Home range, occupancy and deviation history for ${params.tigerId}.`,
      },
    ],
  }),
  component: TigerDetail,
});

function TigerDetail() {
  const { tigerId } = Route.useParams();
  const { data } = useDataset();
  const cameras = data?.cameras ?? [];
  const sightings = data?.sightings ?? [];
  const tiger = data?.tigers.find((t) => t.tiger_id === tigerId);
  const occ = computeOccupancy(tigerId, sightings, cameras);
  const own = sightings
    .filter((s) => s.tiger_id === tigerId)
    .sort((a, b) => b.timestamp.localeCompare(a.timestamp));
  const alerts = data ? generateAlerts(sightings, cameras).filter((a) => a.tiger_id === tigerId) : [];

  return (
    <AppShell
      title={tiger?.name ? `${tigerId} · ${tiger.name}` : tigerId}
      subtitle={`${occ.sightings} captures across ${occ.stations.length} stations`}
      actions={
        <div className="flex gap-2">
          <Button asChild variant="ghost">
            <Link to="/tigers">
              <ArrowLeft className="mr-2 size-4" /> Catalogue
            </Link>
          </Button>
          <Button
            variant="secondary"
            onClick={() =>
              downloadCsv(
                `${tigerId}-captures.csv`,
                own.map((s) => ({
                  sighting_id: s.sighting_id,
                  timestamp: s.timestamp,
                  station: s.camera_id ?? "",
                  location: s.location_name ?? "",
                  latitude: s.latitude ?? "",
                  longitude: s.longitude ?? "",
                  similarity: s.similarity_score ?? "",
                  review: s.review_status ?? "auto",
                })),
              )
            }
          >
            <Download className="mr-2 size-4" /> Export captures
          </Button>
        </div>
      }
    >
      <div className="grid gap-4 sm:grid-cols-4">
        <Stat label="Home range (MCP)" value={`${occ.areaKm2.toFixed(1)} km²`} />
        <Stat
          label="Activity centroid"
          value={
            occ.centroid ? `${occ.centroid.lat.toFixed(4)}, ${occ.centroid.lng.toFixed(4)}` : "—"
          }
        />
        <Stat label="Max span" value={`${occ.maxSpanKm.toFixed(1)} km`} />
        <Stat label="Last seen" value={occ.lastSeen?.slice(0, 10) ?? "—"} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card className="panel lg:col-span-2">
          <CardHeader>
            <CardTitle>Range and capture locations</CardTitle>
            <CardDescription>
              Minimum convex polygon over all GPS-tagged captures for this individual.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <MapPanel
              cameras={cameras}
              ranges={[occ]}
              height={400}
              {...(occ.centroid
                ? { center: [occ.centroid.lat, occ.centroid.lng] as [number, number], zoom: 12 }
                : {})}
            />
          </CardContent>
        </Card>

        <Card className="panel">
          <CardHeader>
            <CardTitle className="text-base">Alerts for this individual</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {alerts.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No deviation from established history.
              </p>
            ) : (
              alerts.map((a) => (
                <div key={a.id} className="rounded-md border border-border p-3">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm font-medium">{a.title}</p>
                    <Badge variant={a.severity === "critical" ? "destructive" : "secondary"}>
                      {a.severity}
                    </Badge>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">{a.what_changed}</p>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="panel mt-6">
        <CardHeader>
          <CardTitle>Capture history</CardTitle>
          <CardDescription>
            Every automated identification can be confirmed or flagged by a reviewer.
          </CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Timestamp</TableHead>
                <TableHead>Station</TableHead>
                <TableHead>Location</TableHead>
                <TableHead>GPS</TableHead>
                <TableHead>Stripe similarity</TableHead>
                <TableHead className="text-right">Review</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {own.map((s) => (
                <TableRow key={s.sighting_id}>
                  <TableCell className="font-mono text-xs">
                    {s.timestamp.slice(0, 16).replace("T", " ")}
                  </TableCell>
                  <TableCell className="font-mono text-xs">{s.camera_id}</TableCell>
                  <TableCell className="text-sm">{s.location_name}</TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {s.latitude?.toFixed(4)}, {s.longitude?.toFixed(4)}
                  </TableCell>
                  <TableCell>
                    <Badge variant={(s.similarity_score ?? 0) >= 0.78 ? "secondary" : "outline"}>
                      {((s.similarity_score ?? 0) * 100).toFixed(1)}%
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    {s.review_status === "needs-review" ? (
                      <div className="flex justify-end gap-1">
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => toast.success(`${s.sighting_id} confirmed as ${tigerId}`)}
                        >
                          <Check className="size-3.5" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => toast(`${s.sighting_id} sent to the review queue`)}
                        >
                          <Flag className="size-3.5" />
                        </Button>
                      </div>
                    ) : (
                      <span className="text-xs text-muted-foreground">auto-matched</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </AppShell>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card className="panel">
      <CardContent className="pt-6">
        <p className="text-xs text-muted-foreground uppercase">{label}</p>
        <p className="mt-1 text-lg font-semibold">{value}</p>
      </CardContent>
    </Card>
  );
}
