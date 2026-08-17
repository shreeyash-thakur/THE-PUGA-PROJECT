import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { getApiBase, loadDataset, type Dataset } from "./api";

export function useHydrated() {
  const [h, setH] = useState(false);
  useEffect(() => setH(true), []);
  return h;
}

export function useApiBase() {
  const hydrated = useHydrated();
  return hydrated ? getApiBase() : "";
}

export function useDataset() {
  const base = useApiBase();
  return useQuery<Dataset>({
    queryKey: ["puga-dataset", base],
    queryFn: ({ signal }) => loadDataset(base, signal),
    staleTime: 30_000,
  });
}
