import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Plug, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { DEFAULT_API_BASE, getApiBase, setApiBase } from "@/lib/puga/api";
import { useDataset, useHydrated } from "@/lib/puga/use-dataset";

export const Route = createFileRoute("/settings")({
  head: () => ({
    meta: [
      { title: "Settings — PUGA offline triage system" },
      {
        name: "description",
        content:
          "Point the console at your local PUGA processing service, verify connectivity and review the offline-first data handling rules.",
      },
      { property: "og:title", content: "Settings — PUGA" },
      {
        property: "og:description",
        content: "Configure the local backend endpoint for the camera trap triage console.",
      },
    ],
  }),
  component: SettingsPage,
});

function SettingsPage() {
  const hydrated = useHydrated();
  const { data, refetch, isFetching } = useDataset();
  const [url, setUrl] = useState(() => (hydrated ? getApiBase() : DEFAULT_API_BASE));
  const live = data?.source === "live";

  function save(next: string) {
    setApiBase(next);
    setUrl(next);
    void refetch();
    toast.success("Endpoint saved — re-checking the local service");
  }

  return (
    <AppShell
      title="Settings"
      subtitle="The console runs entirely on the reserve's own hardware."
    >
      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="panel">
          <CardHeader>
            <CardTitle>Local processing service</CardTitle>
            <CardDescription>
              The FastAPI service that performs blank filtering, stripe matching and database
              writes. When it is unreachable the console shows an empty state — no
              demonstration or sample data is ever displayed in its place.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="api">Service base URL</Label>
              <Input
                id="api"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder={DEFAULT_API_BASE}
                spellCheck={false}
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => save(url.trim().replace(/\/$/, ""))}>
                <Plug className="mr-2 size-4" /> Save & test
              </Button>
              <Button variant="ghost" onClick={() => save(DEFAULT_API_BASE)}>
                <RotateCcw className="mr-2 size-4" /> Reset
              </Button>
            </div>
            <div className="flex items-center gap-2 rounded-md border border-border p-3 text-sm">
              <Badge variant={live ? "secondary" : "outline"}>
                {isFetching ? "checking" : live ? "live backend" : "demo dataset"}
              </Badge>
              <span className="text-muted-foreground">
                {live
                  ? "Connected to the local processing service."
                  : "No local service detected — showing the bundled Pench demonstration dataset."}
              </span>
            </div>
          </CardContent>
        </Card>

        <Card className="panel">
          <CardHeader>
            <CardTitle>Operating rules</CardTitle>
            <CardDescription>Constraints this build is designed around.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-muted-foreground">
            <Rule title="Offline-first">
              Images never leave the reserve. All processing runs on the field laptop; the console
              only reads from the local service.
            </Rule>
            <Rule title="Nothing is deleted">
              Blank and low-value frames are quarantined, never destroyed, and can be restored from
              the quarantine review screen.
            </Rule>
            <Rule title="Human-in-the-loop">
              Low-confidence stripe matches are queued for reviewer confirmation instead of being
              written silently into the individual database.
            </Rule>
            <Rule title="Auditable alerts">
              Each alert records what changed, the supporting captures and a confidence level, and
              survey-effort artefacts are labelled rather than raised as movement.
            </Rule>
            <Rule title="Privacy">
              Frames containing people are held for restricted review and excluded from exports.
            </Rule>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}

function Rule({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-md border border-border p-3">
      <p className="font-medium text-foreground">{title}</p>
      <p className="mt-1">{children}</p>
    </div>
  );
}
