"use client";

import { useChaotingStore } from "@/lib/store";
import type { ZouzheListItem } from "@/lib/types";
import { createContext, useContext, useEffect, useRef } from "react";

interface SSEContextValue {
  connected: boolean;
}

const SSEContext = createContext<SSEContextValue>({ connected: false });

export function useSSE() {
  return useContext(SSEContext);
}

export function SSEProvider({ children }: { children: React.ReactNode }) {
  const setSseConnected = useChaotingStore((s) => s.setSseConnected);
  const applyZouzheUpdate = useChaotingStore((s) => s.applyZouzheUpdate);
  const appendZoubaoEntry = useChaotingStore((s) => s.appendZoubaoEntry);
  const sseConnected = useChaotingStore((s) => s.sseConnected);
  const retryRef = useRef(0);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    let cancelled = false;

    function connect() {
      if (cancelled) return;

      const es = new EventSource("/api/stream");
      esRef.current = es;

      es.onopen = () => {
        setSseConnected(true);
        retryRef.current = 0;
      };

      es.addEventListener("heartbeat", () => {
        // Keep-alive, no action needed
      });

      es.addEventListener("zouzhe_update", (event) => {
        try {
          const data = JSON.parse(event.data) as ZouzheListItem;
          applyZouzheUpdate(data);
        } catch {
          // Ignore parse errors
        }
      });

      es.addEventListener("zoubao_new", (event) => {
        try {
          const data = JSON.parse(event.data);
          appendZoubaoEntry(data.zouzhe_id, {
            id: data.id,
            agent_id: data.agent_id,
            text: data.text,
            todos_json: data.todos_json,
            tokens_used: data.tokens_used,
            timestamp: data.timestamp,
          });
        } catch {
          /* ignore */
        }
      });

      es.onerror = () => {
        setSseConnected(false);
        es.close();
        esRef.current = null;

        if (!cancelled) {
          // Exponential backoff: 1s, 2s, 4s, 8s, max 30s
          const delay = Math.min(1000 * 2 ** retryRef.current, 30000);
          retryRef.current++;
          setTimeout(connect, delay);
        }
      };
    }

    connect();

    return () => {
      cancelled = true;
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
      setSseConnected(false);
    };
  }, [setSseConnected, applyZouzheUpdate, appendZoubaoEntry]);

  return (
    <SSEContext.Provider value={{ connected: sseConnected }}>
      {children}
    </SSEContext.Provider>
  );
}
