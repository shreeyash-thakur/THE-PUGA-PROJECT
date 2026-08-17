import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Download } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { DEFAULT_ALERT_CONFIG, generateAlerts, type AlertConfig } from "@/lib/puga/alerts";
import { downloadCsv } from "@/lib/puga/export";
import { useDataset } from "@/lib/puga/use-dataset";

export const Route = createFileRoute("/alerts")({
  head: () => ({
    meta: [
      { title: "Deviation alerts — PUGA" },
      {
        name: "description",
        content:
          "Actionable movement-deviation alerts: centroid shifts, first captures at new stations, buffer and village-adjacent movement, and prolonged absence.",
      },
      { property: "og:title", content: "Deviation alerts — PUGA" },
      {
        property: "og:description",
        content:
          "Each alert states what changed, the supporting evidence and a confidence level — survey-effort artefacts are separated out.",
      },
    ],
  }),
  component: AlertsPage,
});

const TYPE_LABEL: Record<string, string> = {
  "centroid-shift": "Range centroid shift",
  "new-station": "First capture at new station",
  "buffer-movement": "Buffer / village movement",
  "prolonged-absence": "Prolonged absence",
  "effort-artefact": "Survey-effort artefact",
};

function AlertsPage() {
  const { data } = useDataset();
  const [config, setConfig] = useState<AlertConfig>(DEFAULT_ALERT_CONFIG);
  const [showArtefacts, setShowArtefacts] = useState(true);

  const alerts = useMemo(
    () => (data ? generateAlerts(data.sightings, data.cameras, config) : []),
    [data, config],
  );
  const shown = showArtefacts ? alerts : alerts.filter((a) => !a.suppressed);
  const counts = {
    critical: alerts.filter((a) => a.severity === "critical").length,
    warning: alerts.filter((a) => a.severity === "warning").length,
    artefact: alerts.filter((a) => a.suppressed).length,
  };

  return (
    <AppShell
      title="Deviation & trend alerts"
      subtitle="Every run is compared against each individual's established history."
      actions={
        <Button
          variant="secondary"
          onClick={() =>
            downloadCsv(
              "puga-alerts.csv",
              alerts.map((a) => ({
                tiger_id: a.tiger_id,
                type: a.type,
                severity: a.severity,
                title: a.title,
                what_changed: a.what_changed,
                evidence: a.evidence.join(" | "),
                confidence: a.confidence,
                confidence_label: a.confidence_label,
                survey_effort_artefact: a.suppressed ? "yes" : "no",
              })),
            )
          }
        >
          <Download className="mr-2 size-4" /> Export alerts
        </Button>
      }
    >
      <div className="grid gap-6 lg:grid-cols-[minmax(0,320px)_1fr]">
        <div className="space-y-6">
          <Card className="panel">
            <CardHeader>
              <CardTitle className="text-base">Thresholds</CardTitle>
              <CardDescription>Tuned per reserve by the monitoring team.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="space-y-2">
                <Label>Core centroid shift — {config.coreShiftKm.toFixed(1)} km</Label>
                <Slider
                  value={[config.coreShiftKm]}
                  min={1}
                  max={10}
                  step={0.5}
                  onValueChange={(v) => setConfig((c) => ({ ...c, coreShiftKm: v[0] ?? 4.5 }))}
                />
                <p className="text-xs text-muted-foreground">
                  ≈ {(Math.PI * config.coreShiftKm ** 2).toFixed(0)} km² of displaced range.
                </p>
              </div>
              <div className="space-y-2">
                <Label>Buffer centroid shift — {config.bufferShiftKm.toFixed(1)} km</Label>
                <Slider
                  value={[config.bufferShiftKm]}
                  min={1}
                  max={10}
                  step={0.5}
                  onValueChange={(v) => setConfig((c) => ({ ...c, bufferShiftKm: v[0] ?? 5 }))}
                />
              </div>
              <div className="space-y-2">
                <Label>Absence threshold — {config.absenceDays} days</Label>
                <Slider
                  value={[config.absenceDays]}
                  min={30}
                  max={365}
                  step={15}
                  onValueChange={(v) => setConfig((c) => ({ ...c, absenceDays: v[0] ?? 120 }))}
                />
              </div>
              <div className="space-y-2">
                <Label>Current run window — {config.runWindowDays} days</Label>
                <Slider
                  value={[config.runWindowDays]}
                  min={30}
                  max={240}
                  step={15}
                  onValueChange={(v) => setConfig((c) => ({ ...c, runWindowDays: v[0] ?? 90 }))}
                />
              </div>
              <div className="flex items-center justify-between rounded-md border border-border p-3">
                <div>
                  <p className="text-sm font-medium">Show effort artefacts</p>
                  <p className="text-xs text-muted-foreground">
                    New camera ≠ new movement — kept visible but never raised as deviation.
                  </p>
                </div>
                <Switch checked={showArtefacts} onCheckedChange={setShowArtefacts} />
              </div>
            </CardContent>
          </Card>

          <Card className="panel">
            <CardContent className="space-y-2 pt-6 text-sm">
              <Row label="Critical" value={counts.critical} />
              <Row label="Warning" value={counts.warning} />
              <Row label="Effort artefacts (suppressed)" value={counts.artefact} />
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          {shown.map((a) => (
            <Card
              key={a.id}
              className={`panel ${a.suppressed ? "opacity-70" : ""} ${
                a.severity === "critical" ? "border-destructive/50" : ""
              }`}
            >
              <CardHeader className="flex-row items-start justify-between gap-4">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline">{TYPE_LABEL[a.type]}</Badge>
                    <Badge variant={a.severity === "critical" ? "destructive" : "secondary"}>
                      {a.severity}
                    </Badge>
                    {a.suppressed ? <Badge variant="outline">suppressed</Badge> : null}
                  </div>
                  <CardTitle className="mt-2 text-base">{a.title}</CardTitle>
                  <CardDescription className="mt-1">{a.what_changed}</CardDescription>
                </div>
                <div className="text-right">
                  <p className="text-xs text-muted-foreground">confidence</p>
                  <p className="text-lg font-semibold">{a.confidence_label}</p>
                  <p className="text-xs text-muted-foreground">{a.confidence}</p>
                </div>
              </CardHeader>
              <CardContent>
                <p className="mb-2 text-xs tracking-wide text-muted-foreground uppercase">
                  Supporting evidence
                </p>
                <ul className="space-y-1 text-sm text-muted-foreground">
                  {a.evidence.map((e) => (
                    <li key={e} className="flex gap-2">
                      <span className="text-primary">•</span>
                      {e}
                    </li>
                  ))}
                </ul>
                <Button asChild size="sm" variant="ghost" className="mt-3 px-0">
                  <Link to="/tigers/$tigerId" params={{ tigerId: a.tiger_id }}>
                    Open {a.tiger_id} profile →
                  </Link>
                </Button>
              </CardContent>
            </Card>
          ))}
          {shown.length === 0 ? (
            <Card className="panel">
              <CardContent className="py-16 text-center text-muted-foreground">
                No alerts at the current thresholds.
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
    </AppShell>
  );
}

function Row({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-semibold">{value}</span>
    </div>
  );
}
