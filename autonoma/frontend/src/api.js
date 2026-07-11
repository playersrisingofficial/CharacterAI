// Thin API client + live event hook shared by the SPA.
import { useEffect, useRef, useState } from "react";

const API = "/api/v1";

export async function api(path, opts) {
  const r = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!r.ok && r.status !== 204) throw new Error((await r.text()) || String(r.status));
  return r.status === 204 ? null : r.json();
}

// Subscribe to the global live event stream over WebSocket. Returns the most
// recent events and a monotonically increasing tick that consumers can use to
// trigger refetches.
export function useLiveEvents() {
  const [events, setEvents] = useState([]);
  const [tick, setTick] = useState(0);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);

  useEffect(() => {
    let stop = false;
    function connect() {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}${API}/monitor/events/ws`);
      wsRef.current = ws;
      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (!stop) setTimeout(connect, 2000);
      };
      ws.onmessage = (m) => {
        const ev = JSON.parse(m.data);
        setEvents((prev) => [ev, ...prev].slice(0, 150));
        setTick((t) => t + 1);
      };
    }
    connect();
    return () => {
      stop = true;
      wsRef.current?.close();
    };
  }, []);

  return { events, tick, connected };
}
