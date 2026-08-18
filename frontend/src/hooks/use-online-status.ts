import * as React from "react";

/** Tracks the browser's connectivity (navigator.onLine + the online/
 * offline events). This reflects whether the *device* has a network
 * link at all — it says nothing about whether the PUGA backend itself
 * is reachable (see `useDataset`'s "live"/"offline" dataset source for
 * that). Used to explain why the map is showing cached tiles / a stale
 * dataset instead of failing silently. */
export function useOnlineStatus(): boolean {
  const [isOnline, setIsOnline] = React.useState(true);

  React.useEffect(() => {
    setIsOnline(navigator.onLine);
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  return isOnline;
}
