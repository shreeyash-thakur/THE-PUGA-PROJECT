import { Link } from "@tanstack/react-router";
import {
  Bell,
  Cat,
  FolderInput,
  LayoutDashboard,
  Map as MapIcon,
  Settings,
  ShieldAlert,
} from "lucide-react";
import type { ReactNode } from "react";
import { useDataset } from "@/lib/puga/use-dataset";
import { Badge } from "@/components/ui/badge";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/ingest", label: "Ingest run", icon: FolderInput },
  { to: "/quarantine", label: "Quarantine", icon: ShieldAlert },
  { to: "/tigers", label: "Individuals", icon: Cat },
  { to: "/occupancy", label: "Occupancy map", icon: MapIcon },
  { to: "/alerts", label: "Alerts", icon: Bell },
  { to: "/settings", label: "Settings", icon: Settings },
] as const;

export function AppShell({
  title,
  subtitle,
  actions,
  children,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  const { data } = useDataset();

  return (
    <div className="min-h-screen lg:flex">
      <aside className="border-b border-border bg-sidebar lg:min-h-screen lg:w-64 lg:shrink-0 lg:border-r lg:border-b-0">
        <div className="flex items-center gap-3 px-5 py-5">
          <div className="grid size-10 place-items-center rounded-md bg-primary/15 text-primary">
            <Cat className="size-5" />
          </div>
          <div>
            <p className="text-sm font-semibold tracking-wide">PUGA</p>
            <p className="text-xs text-muted-foreground">Pench Tiger Reserve</p>
          </div>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 pb-3 lg:flex-col lg:overflow-visible">
          {NAV.map(({ to, label, icon: Icon }) => (
            <Link
              key={to}
              to={to}
              className="flex items-center gap-2 rounded-md px-3 py-2 text-sm whitespace-nowrap text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground"
              activeProps={{ className: "bg-sidebar-accent text-foreground font-medium" }}
              activeOptions={{ exact: to === "/" }}
            >
              <Icon className="size-4" />
              {label}
            </Link>
          ))}
        </nav>
        <div className="hidden px-5 py-4 lg:block">
          <Badge variant={data?.source === "live" ? "default" : "destructive"}>
            {data?.source === "live" ? "Live backend" : "Backend unreachable"}
          </Badge>
          <p className="mt-2 text-xs text-muted-foreground">
            {data?.source === "live"
              ? data.baseUrl
              : `Start the PUGA backend and check the URL in Settings (${data?.baseUrl ?? "http://localhost:8000"}).`}
          </p>
        </div>
      </aside>

      <main className="min-w-0 flex-1">
        <header className="flex flex-wrap items-end justify-between gap-4 border-b border-border px-6 py-6">
          <div>
            <h1 className="text-2xl font-semibold">{title}</h1>
            {subtitle ? (
              <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
            ) : null}
          </div>
          {actions}
        </header>
        <div className="px-6 py-6">{children}</div>
      </main>
    </div>
  );
}
