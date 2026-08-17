import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Download, Search } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { computeOccupancy } from "@/lib/puga/occupancy";
import { useDataset } from "@/lib/puga/use-dataset";
import { downloadCsv } from "@/lib/puga/export";

export const Route = createFileRoute("/tigers/")({
  head: () => ({
    meta: [
      { title: "Individual tiger database — PUGA" },
      {
        name: "description",
        content:
          "Persistent, queryable catalogue of individually identified tigers with stations, timestamps and GPS captures.",
      },
      { property: "og:title", content: "Individual tiger database — PUGA" },
      {
        property: "og:description",
        content: "Stripe-pattern identification results, enrolment history and review queue.",
      },
    ],
  }),
  component: TigersPage,
});

function TigersPage() {
  const { data } = useDataset();
  const [q, setQ] = useState("");

  const rows = useMemo(() => {
    const cams = data?.cameras ?? [];
    const sightings = data?.sightings ?? [];
    return (data?.tigers ?? [])
      .map((t) => ({ tiger: t, occ: computeOccupancy(t.tiger_id, sightings, cams) }))
      .filter(({ tiger }) =>
        q
          ? tiger.tiger_id.toLowerCase().includes(q.toLowerCase()) ||
            (tiger.name ?? "").toLowerCase().includes(q.toLowerCase())
          : true,
      );
  }, [data, q]);

  const needsReview = (data?.sightings ?? []).filter((s) => s.review_status === "needs-review");

  return (
    <AppShell
      title="Individual database"
      subtitle="Confident stripe matches are applied automatically; ambiguous ones wait for a reviewer."
      actions={
        <Button
          variant="secondary"
          onClick={() =>
            downloadCsv(
              "puga-individuals.csv",
              rows.map(({ tiger, occ }) => ({
                tiger_id: tiger.tiger_id,
                name: tiger.name ?? "",
                status: tiger.status,
                captures: occ.sightings,
                stations: occ.stations.join(" "),
                area_km2: occ.areaKm2.toFixed(2),
                centroid_lat: occ.centroid?.lat.toFixed(5) ?? "",
                centroid_lng: occ.centroid?.lng.toFixed(5) ?? "",
                first_seen: occ.firstSeen ?? "",
                last_seen: occ.lastSeen ?? "",
              })),
            )
          }
        >
          <Download className="mr-2 size-4" /> Export CSV
        </Button>
      }
    >
      <Card className="panel">
        <CardHeader className="flex-row items-center justify-between gap-4">
          <div>
            <CardTitle>Catalogue</CardTitle>
            <CardDescription>
              {rows.length} individuals · {needsReview.length} captures awaiting human review
            </CardDescription>
          </div>
          <div className="relative w-64 max-w-full">
            <Search className="absolute top-2.5 left-2.5 size-4 text-muted-foreground" />
            <Input
              className="pl-8"
              placeholder="Search ID or name"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Captures</TableHead>
                <TableHead>Stations</TableHead>
                <TableHead>Range (MCP)</TableHead>
                <TableHead>Last seen</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map(({ tiger, occ }) => (
                <TableRow key={tiger.tiger_id} className="cursor-pointer">
                  <TableCell className="font-mono text-xs">
                    <Link
                      to="/tigers/$tigerId"
                      params={{ tigerId: tiger.tiger_id }}
                      className="text-primary hover:underline"
                    >
                      {tiger.tiger_id}
                    </Link>
                  </TableCell>
                  <TableCell>{tiger.name ?? <span className="text-muted-foreground">unnamed</span>}</TableCell>
                  <TableCell>
                    <Badge variant={tiger.status === "active" ? "secondary" : "outline"}>
                      {tiger.status}
                    </Badge>
                  </TableCell>
                  <TableCell>{occ.sightings}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {occ.stations.length}
                  </TableCell>
                  <TableCell>{occ.areaKm2.toFixed(1)} km²</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {occ.lastSeen?.slice(0, 10) ?? "—"}
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
