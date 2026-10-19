"use client";

import { useEffect, useState } from "react";

type Status = "connecting" | "connected" | "closed" | "error";

// public/config.json is written at deploy time by infra/deploy.sh: {"stubUrl": "https://..."}
async function loadStubUrl(): Promise<string> {
  const res = await fetch("/config.json");
  const { stubUrl } = (await res.json()) as { stubUrl: string };
  return stubUrl;
}

export default function Page() {
  const [status, setStatus] = useState<Status>("connecting");
  const [card, setCard] = useState<string | null>(null);
  const [stubUrl, setStubUrl] = useState<string | null>(null);

  useEffect(() => {
    let ws: WebSocket | undefined;
    let cancelled = false;

    async function connect() {
      try {
        const base = await loadStubUrl();
        setStubUrl(base);
        const res = await fetch(`${base}/negotiate`);
        const { url } = (await res.json()) as { url: string | null };
        if (!url) throw new Error("Web PubSub is not configured on the stub");
        if (cancelled) return;
        ws = new WebSocket(url);
        ws.onopen = () => setStatus("connected");
        ws.onclose = () => setStatus("closed");
        ws.onerror = () => setStatus("error");
        ws.onmessage = (m) => {
          try {
            setCard(JSON.stringify(JSON.parse(m.data as string), null, 2));
          } catch {
            setCard(String(m.data));
          }
        };
      } catch {
        if (!cancelled) setStatus("error");
      }
    }

    connect();
    return () => {
      cancelled = true;
      ws?.close();
    };
  }, []);

  return (
    <main>
      <h1>The Dugout</h1>
      <p>Web PubSub: {status}</p>
      <button disabled={!stubUrl} onClick={() => fetch(`${stubUrl}/push`, { method: "POST" })}>
        Push stub card
      </button>
      <pre>{card ?? "Waiting for a card."}</pre>
    </main>
  );
}
