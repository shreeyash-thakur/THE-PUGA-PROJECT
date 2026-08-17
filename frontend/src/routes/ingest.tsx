import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";
import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { runBatch } from "@/lib/puga/api";
import { useApiBase, useDataset } from "@/lib/puga/use-dataset";
import type { BatchSummary } from "@/lib/puga/types";

export const Route = createFileRoute("/ingest")({
  head: () => ({
    meta: [
      { title: "Ingest run — PUGA camera trap triage" },
      {
        name: "description",
        content:
          "Point PUGA at a raw SD-card folder to detect blanks, quarantine them safely and identify individual tigers.",
      },
      { property: "og:title", content: "Ingest run — PUGA" },
      {
        property: "og:description",
        content: "Raw camera trap folder ingestion with safe, reversible blank removal.",
      },
    ],
  }),
  component: IngestPage,
});

const STAGES = [
  "Scanning folders & reading EXIF",
  "Hashing files / de-duplicating SD cards",
  "MegaDetector blank vs subject classification",
  "Quarantining blanks (staged, reversible)",
  "Cropping flanks & extracting stripe embeddings",
  "Matching against individual catalogue",
  "Regenerating occupancy & deviation alerts",
];

function IngestPage() {
  const base = useApiBase();
  const { data } = useDataset();
  const [folder, setFolder] = useState("/media/sdcard/PENCH_CYCLE_2026_C1");
  const [station, setStation] = useState("");
  const [threshold, setThreshold] = useState(0.2);
  const [recursive, setRecursive] = useState(true);
  const [running, setRunning] = useState(false);
  const [stage, setStage] = useState(-1);
  const [summary, setSummary] = useState<BatchSummary | null>(null);

  async function start() {
    if (!folder.trim()) {
      toast.error("Enter the folder path from the SD card.");
      return;
    }
    setRunning(true);
    setSummary(null);

    if (base) {
      try {
        setStage(0);
        const res = await runBatch(base, {
          folder_path: folder,
          ...(station ? { camera_id: station } : {}),
          detection_threshold: threshold,
          recursive,
        });
        setSummary(res);
        toast.success(`Batch ${res.batch_id} completed`);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Batch failed");
      } finally {
        setStage(-1);
        setRunning(false);
      }
      return;
    }

    // Demo mode: replay the bundled sample run stage by stage.
    for (let i = 0; i < STAGES.length; i++) {
      setStage(i);
      await new Promise((r) => setTimeout(r, 550));
    }
    setStage(-1);
    setRunning(false);
    setSummary(data?.lastBatch ?? null);
    toast.success("Sample run replayed — connect a local backend for real folders.");
  }

  return (
    <AppShell
      title="Ingest run"
      subtitle="Raw, unprocessed camera trap folders exactly as they come off the field SD cards."
    >
      <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_1fr]">
        <Card className="panel">
          <CardHeader>
            <CardTitle>Source folder</CardTitle>
            <CardDescription>
              {base
                ? `Processed locally by the PUGA backend at ${base}.`
                : "No backend configured — this replays the bundled sample run."}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="folder">Folder path</Label>
              <Input id="folder" value={folder} onChange={(e) => setFolder(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="station">Station override (optional)</Label>
              <Input
                id="station"
                placeholder="e.g. PTR-C04 — leave blank to infer from folder names"
                value={station}
                onChange={(e) => setStation(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label>Detection confidence threshold — {threshold.toFixed(2)}</Label>
              <Slider
                value={[threshold]}
                min={0.05}
                max={0.6}
                step={0.05}
                onValueChange={(v) => setThreshold(v[0] ?? 0.2)}
              />
              <p className="text-xs text-muted-foreground">
                Lower keeps more frames — deliberately biased against false negatives, since a
                discarded animal frame is irreplaceable.
              </p>
            </div>
            <div className="flex items-center justify-between rounded-md border border-border p-3">
              <div>
                <p className="text-sm font-medium">Recurse into subfolders</p>
                <p className="text-xs text-muted-foreground">Handles messy SD-card trees.</p>
              </div>
              <Switch checked={recursive} onCheckedChange={setRecursive} />
            </div>
            <Button className="w-full" onClick={start} disabled={running}>
              {running ? "Processing…" : "Start ingest"}
            </Button>
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card className="panel">
            <CardHeader>
              <CardTitle>Pipeline</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {STAGES.map((s, i) => {
                const done = stage > i || (!running && summary !== null);
                const active = stage === i;
                return (
                  <div key={s} className="flex items-center gap-3">
                    <span
                      className={`size-2.5 rounded-full ${
                        active
                          ? "animate-pulse bg-primary"
                          : done
                            ? "bg-success"
                            : "bg-muted-foreground/30"
                      }`}
                    />
                    <span
                      className={`text-sm ${active || done ? "text-foreground" : "text-muted-foreground"}`}
                    >
                      {s}
                    </span>
                  </div>
                );
              })}
              {running ? (
                <Progress value={((stage + 1) / STAGES.length) * 100} className="mt-2" />
              ) : null}
            </CardContent>
          </Card>

          {summary ? (
            <Card className="panel">
              <CardHeader className="flex-row items-center justify-between">
                <CardTitle>Run summary — {summary.batch_id}</CardTitle>
                <Badge variant="secondary">{summary.status}</Badge>
              </CardHeader>
              <CardContent>
                <div className="grid gap-4 sm:grid-cols-3">
                  <Metric label="Frames ingested" value={summary.total_images.toLocaleString()} />
                  <Metric
                    label="Blanks quarantined"
                    value={summary.quarantined.toLocaleString()}
                  />
                  <Metric
                    label="Frames with subject"
                    value={summary.animal_detected.toLocaleString()}
                  />
                  <Metric label="Duplicates" value={summary.duplicates.toLocaleString()} />
                  <Metric label="Unreadable" value={summary.failed.toLocaleString()} />
                  <Metric
                    label="Reclaimable"
                    value={`${(summary.storage.reclaimable_storage_bytes / 1e9).toFixed(1)} GB`}
                  />
                </div>
                {summary.warnings?.length ? (
                  <div className="mt-4 space-y-2">
                    <p className="text-xs tracking-wide text-muted-foreground uppercase">
                      Flagged field realities
                    </p>
                    {summary.warnings.map((w) => (
                      <p key={w} className="rounded-md bg-secondary/60 p-2 text-xs">
                        {w}
                      </p>
                    ))}
                  </div>
                ) : null}
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
    </AppShell>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-semibold">{value}</p>
    </div>
  );
}
