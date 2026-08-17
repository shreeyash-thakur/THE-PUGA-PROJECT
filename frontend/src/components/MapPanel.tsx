import { lazy, Suspense } from "react";
import { useHydrated } from "@/lib/puga/use-dataset";
import type { ReserveMapProps } from "./ReserveMap";

const ReserveMap = lazy(() => import("./ReserveMap"));

export function MapPanel(props: ReserveMapProps) {
  const hydrated = useHydrated();
  const height = props.height ?? 520;

  if (!hydrated) {
    return (
      <div
        className="grid animate-pulse place-items-center rounded-xl border border-border bg-muted/40 text-sm text-muted-foreground"
        style={{ height }}
      >
        Loading reserve map…
      </div>
    );
  }

  return (
    <Suspense
      fallback={
        <div
          className="grid place-items-center rounded-xl border border-border bg-muted/40 text-sm text-muted-foreground"
          style={{ height }}
        >
          Loading reserve map…
        </div>
      }
    >
      <ReserveMap {...props} />
    </Suspense>
  );
}
