import { useEffect, useRef, useState, useCallback } from "react";
import { Snapshot, wsUrl, api } from "../api";

export type ConnState = "connecting" | "live" | "offline";

// Connects to the backend WebSocket for live snapshots, with auto-reconnect
// and a REST fallback so the UI still populates if the socket is unavailable.
export function useLiveState() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [conn, setConn] = useState<ConnState>("connecting");
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef<number>(0);
  const aliveRef = useRef(true);

  const connect = useCallback(() => {
    setConn("connecting");
    let ws: WebSocket;
    try {
      ws = new WebSocket(wsUrl());
    } catch {
      setConn("offline");
      return;
    }
    wsRef.current = ws;

    ws.onopen = () => {
      retryRef.current = 0;
      setConn("live");
    };
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as Snapshot;
        if (data && data.bankroll) setSnapshot(data);
      } catch {
        /* ignore malformed frames */
      }
    };
    ws.onclose = () => {
      if (!aliveRef.current) return;
      setConn("offline");
      const delay = Math.min(1000 * 2 ** retryRef.current, 8000);
      retryRef.current += 1;
      // REST fallback while reconnecting
      api.state().then(setSnapshot).catch(() => {});
      window.setTimeout(connect, delay);
    };
    ws.onerror = () => ws.close();
  }, []);

  useEffect(() => {
    aliveRef.current = true;
    // Prime immediately via REST, then upgrade to the socket.
    api.state().then(setSnapshot).catch(() => {});
    connect();
    return () => {
      aliveRef.current = false;
      wsRef.current?.close();
    };
  }, [connect]);

  return { snapshot, conn };
}
