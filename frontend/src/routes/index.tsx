import { createFileRoute, Link } from "@tanstack/react-router";
import { AlertTriangle, Cat, HardDrive, ImageOff, Timer } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { MapPanel } from "@/components/MapPanel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { generateAlerts } from "@/lib/puga/alerts";
import { computeOccupancy } from "@/lib/puga/occupancy";
import { useDataset } from "@/lib/puga/use-dataset";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "PUGA — Camera Trap Triage & Tiger Movement Intelligence" },
      {
        name: "description",
        content:
          "Offline-first camera trap triage, individual tiger identification, occupancy mapping and movement deviation alerts for Pench Tiger Reserve.",
      },
      { property: "og:title", content: "PUGA — Tiger Movement Intelligence" },
      {
        property: "og:description",
        content:
          "Blank-frame filtering, stripe-pattern individual ID, occupancy maps and actionable deviation alerts on ordinary field hardware.",
      },
    ],
  }),
  component: Dashboard,
});

function gb(bytes: number) {
  return `${(bytes / 1e9).toFixed(1)} GB`;
}

function Dashboard() {
  const { data } = useDataset();
  const batch = data?.lastBatch;
  const tigers = data?.tigers ?? [];
  const sightings = data?.sightings ?? [];
  const cameras = data?.cameras ?? [];
  const alerts = data ? generateAlerts(sightings, cameras) : [];
  const live = alerts.filter((a) => !a.suppressed);
  const ranges = tigers.map((t) => computeOccupancy(t.tiger_id, sightings, cameras));

  const removedPct = batch ? (batch.quarantined / Math.max(batch.total_images, 1)) * 100 : 0;
  const hoursSaved = batch ? Math.round((batch.quarantined * 4) / 3600) : 0;

  return (
    <AppShell
      title="Monitoring cycle overview"
      subtitle="Raw SD-card folders in, individual tiger intelligence out."
      actions={
        <div className="flex gap-2">
          <Button asChild variant="secondary">
            <Link to="/quarantine">Review quarantine</Link>
          </Button>
          <Button asChild>
            <Link to="/ingest">Start ingest run</Link>
          </Button>
        </div>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          icon={<ImageOff className="size-4" />}
          label="Blanks quarantined"
          value={batch ? batch.quarantined.toLocaleString() : "—"}
          hint={`${removedPct.toFixed(1)}% of ${batch?.total_images.toLocaleString() ?? 0} frames`}
        />
        <Stat
          icon={<Cat className="size-4" />}
          label="Individuals in catalogue"
          value={String(tigers.length)}
          hint={`${sightings.length.toLocaleString()} identified captures`}
        />
        <Stat
          icon={<HardDrive className="size-4" />}
          label="Reclaimable storage"
          value={batch ? gb(batch.storage.reclaimable_storage_bytes) : "—"}
          hint={`of ${batch ? gb(batch.storage.original_storage_bytes) : "—"} ingested`}
        />
        <Stat
          icon={<Timer className="size-4" />}
          label="Manual sorting saved"
          value={`~${hoursSaved} h`}
          hint={`run took ${batch ? (batch.processing_time_seconds! / 3600).toFixed(1) : "—"} h on CPU`}
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card className="panel lg:col-span-2">
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Reserve occupancy — all individuals</CardTitle>
            <Button asChild size="sm" variant="ghost">
              <Link to="/occupancy">Open full map</Link>
            </Button>
          </CardHeader>
          <CardContent>
            <MapPanel cameras={cameras} ranges={ranges} height={420} />
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card className="panel">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <AlertTriangle className="size-4 text-warning" />
                Deviation alerts
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {live.slice(0, 4).map((a) => (
                <Link
                  key={a.id}
                  to="/alerts"
                  className="block rounded-md border border-border p-3 transition-colors hover:bg-secondary/60"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium">{a.title}</span>
                    <Badge
                      variant={a.severity === "critical" ? "destructive" : "secondary"}
                      className="shrink-0"
                    >
                      {a.severity}
                    </Badge>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Confidence {a.confidence_label} ({a.confidence})
                  </p>
                </Link>
              ))}
              {live.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No deviations this run.
                </p>
              ) : (
                <Button asChild variant="secondary" className="w-full">
                  <Link to="/alerts">All {live.length} alerts</Link>
                </Button>
              )}
            </CardContent>
          </Card>

          <Card className="panel">
            <CardHeader>
              <CardTitle className="text-base">Last run integrity</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div>
                <div className="mb-1 flex justify-between text-xs text-muted-foreground">
                  <span>Processed</span>
                  <span>
                    {batch?.processed.toLocaleString()} / {batch?.total_images.toLocaleString()}
                  </span>
                </div>
                <Progress value={100} />
              </div>
              {batch?.warnings.map((w) => (
                <p key={w} className="rounded-md bg-secondary/60 p-2 text-xs text-muted-foreground">
                  {w}
                </p>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </AppShell>
  );
}

function Stat({
  icon,
  label,
  value,
  hint,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <Card className="panel">
      <CardContent className="pt-6">
        <div className="flex items-center gap-2 text-xs tracking-wide text-muted-foreground uppercase">
          {icon}
          {label}
        </div>
        <p className="mt-2 text-3xl font-semibold">{value}</p>
        <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  );
}
