import { useCallback, useEffect, useRef, useState } from "react";
import { Dashboard, api } from "../api";

export type ConnState = "loading" | "live" | "offline";

// Polls /api/dashboard on an interval so the UI auto-refreshes without a full
// page reload. The backend recomputes in the background; we just re-read the
// latest stored snapshot.
export function useDashboard(intervalMs = 12000) {
  const [data, setData] = useState<Dashboard | null>(null);
  const [conn, setConn] = useState<ConnState>("loading");
  const [refreshing, setRefreshing] = useState(false);
  const timer = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      const d = await api.dashboard();
      setData(d);
      setConn("live");
    } catch {
      setConn("offline");
    }
  }, []);

  const forceRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await api.refresh();
      await load();
    } catch {
      /* surfaced via conn state */
    } finally {
      setRefreshing(false);
    }
  }, [load]);

  useEffect(() => {
    load();
    timer.current = window.setInterval(load, intervalMs);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [load, intervalMs]);

  return { data, conn, refreshing, forceRefresh };
}
