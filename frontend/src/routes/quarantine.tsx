import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { EyeOff, RotateCcw, Search } from "lucide-react";
import { toast } from "sonner";
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
import { restoreQuarantined } from "@/lib/puga/api";
import { useApiBase, useDataset } from "@/lib/puga/use-dataset";

export const Route = createFileRoute("/quarantine")({
  head: () => ({
    meta: [
      { title: "Quarantine review — PUGA" },
      {
        name: "description",
        content:
          "Staged, reversible deletion of blank camera trap frames with confidence scores, privacy holds and one-click restore.",
      },
      { property: "og:title", content: "Quarantine review — PUGA" },
      {
        property: "og:description",
        content: "Every automated blank-frame decision is auditable and correctable by a human.",
      },
    ],
  }),
  component: QuarantinePage,
});

function QuarantinePage() {
  const base = useApiBase();
  const { data, refetch } = useDataset();
  const [q, setQ] = useState("");
  const [restored, setRestored] = useState<Set<number>>(new Set());

  const items = useMemo(() => {
    const list = data?.quarantine ?? [];
    if (!q) return list;
    const needle = q.toLowerCase();
    return list.filter(
      (i) =>
        i.filename.toLowerCase().includes(needle) ||
        (i.reason ?? "").toLowerCase().includes(needle) ||
        i.original_path.toLowerCase().includes(needle),
    );
  }, [data?.quarantine, q]);

  async function restore(id: number, filename: string) {
    if (base) {
      try {
        await restoreQuarantined(base, id);
        await refetch();
        toast.success(`${filename} restored to its original folder`);
        return;
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Restore failed");
        return;
      }
    }
    setRestored((prev) => new Set(prev).add(id));
    toast.success(`${filename} restored to its original folder`);
  }

  const privacyCount = (data?.quarantine ?? []).filter((i) => i.privacy_hold).length;

  return (
    <AppShell
      title="Quarantine"
      subtitle="Nothing is deleted outright. Blanks are staged here so a misclassified frame is always recoverable."
    >
      <div className="grid gap-4 sm:grid-cols-3">
        <Card className="panel">
          <CardContent className="pt-6">
            <p className="text-xs text-muted-foreground uppercase">Staged frames</p>
            <p className="mt-1 text-3xl font-semibold">{data?.quarantine.length ?? 0}</p>
          </CardContent>
        </Card>
        <Card className="panel">
          <CardContent className="pt-6">
            <p className="text-xs text-muted-foreground uppercase">Restored by reviewers</p>
            <p className="mt-1 text-3xl font-semibold">{restored.size}</p>
          </CardContent>
        </Card>
        <Card className="panel">
          <CardContent className="pt-6">
            <p className="text-xs text-muted-foreground uppercase">Privacy holds (humans)</p>
            <p className="mt-1 text-3xl font-semibold">{privacyCount}</p>
          </CardContent>
        </Card>
      </div>

      <Card className="panel mt-6">
        <CardHeader className="flex-row items-center justify-between gap-4">
          <div>
            <CardTitle>Staged for deletion</CardTitle>
            <CardDescription>
              Purge only happens on explicit confirmation, after review.
            </CardDescription>
          </div>
          <div className="relative w-64 max-w-full">
            <Search className="absolute top-2.5 left-2.5 size-4 text-muted-foreground" />
            <Input
              className="pl-8"
              placeholder="Filter by file, path or reason"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>File</TableHead>
                <TableHead>Original path</TableHead>
                <TableHead>Reason</TableHead>
                <TableHead>Subject confidence</TableHead>
                <TableHead>Captured</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((i) => {
                const isRestored = restored.has(i.id) || i.status === "restored";
                return (
                  <TableRow key={i.id}>
                    <TableCell className="font-mono text-xs">
                      <div className="flex items-center gap-2">
                        {i.privacy_hold ? <EyeOff className="size-3.5 text-warning" /> : null}
                        {i.filename}
                      </div>
                    </TableCell>
                    <TableCell className="max-w-[280px] truncate font-mono text-xs text-muted-foreground">
                      {i.original_path}
                    </TableCell>
                    <TableCell className="text-sm">{i.reason}</TableCell>
                    <TableCell>
                      <Badge variant={(i.confidence ?? 0) > 0.12 ? "secondary" : "outline"}>
                        {((i.confidence ?? 0) * 100).toFixed(1)}%
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {i.capture_timestamp?.slice(0, 16).replace("T", " ")}
                    </TableCell>
                    <TableCell className="text-right">
                      {isRestored ? (
                        <Badge className="bg-success text-success-foreground">Restored</Badge>
                      ) : (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => restore(i.id, i.filename)}
                        >
                          <RotateCcw className="mr-1 size-3.5" /> Restore
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
              {items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="py-10 text-center text-muted-foreground">
                    Nothing in quarantine matches this filter.
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </AppShell>
  );
}
