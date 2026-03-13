"use client";

import { useChaotingStore } from "@/lib/store";
import type { ZoubaoEntry } from "@/lib/types";
import { AnimatePresence, motion } from "framer-motion";
import { useMemo } from "react";

function formatTimestamp(ts: string): string {
  try {
    const d = new Date(ts.endsWith("Z") ? ts : ts + "Z");
    return d.toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return ts;
  }
}

interface ZoubaoFeedProps {
  zouzheId: string;
  initialEntries: ZoubaoEntry[];
}

export function ZoubaoFeed({ zouzheId, initialEntries }: ZoubaoFeedProps) {
  const sseEntries = useChaotingStore(
    (s) => s.detailZoubaoMap[zouzheId] || []
  );

  // Merge initial + SSE entries, deduplicate by id, sort ASC
  const merged = useMemo(() => {
    const map = new Map<number, ZoubaoEntry>();
    for (const e of initialEntries) map.set(e.id, e);
    for (const e of sseEntries) map.set(e.id, e);
    return Array.from(map.values()).sort((a, b) => a.id - b.id);
  }, [initialEntries, sseEntries]);

  if (merged.length === 0) {
    return (
      <div style={{ color: "var(--text-secondary)", fontSize: 13 }}>
        No progress reports
      </div>
    );
  }

  // Running token total
  let runningTokens = 0;

  return (
    <div className="flex flex-col gap-0">
      <AnimatePresence initial={false}>
        {merged.map((entry) => {
          if (entry.tokens_used) runningTokens += entry.tokens_used;
          const currentTotal = runningTokens;

          return (
            <motion.div
              key={entry.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.25 }}
              style={{
                borderBottom: "1px solid var(--border)",
                padding: "12px 0",
              }}
            >
              {/* Header */}
              <div className="flex items-center gap-3 mb-1">
                <span
                  className="font-mono"
                  style={{ fontSize: 11, color: "var(--text-secondary)" }}
                >
                  {formatTimestamp(entry.timestamp)}
                </span>
                {entry.agent_id && (
                  <span
                    style={{
                      fontSize: 11,
                      color: "var(--imperial-gold)",
                      opacity: 0.8,
                    }}
                  >
                    {entry.agent_id}
                  </span>
                )}
              </div>

              {/* Text body */}
              <div
                style={{
                  fontSize: 13,
                  color: "var(--text-primary)",
                  lineHeight: 1.5,
                  whiteSpace: "pre-wrap",
                }}
              >
                {entry.text}
              </div>

              {/* Todos */}
              {entry.todos_json && entry.todos_json.length > 0 && (
                <div className="mt-2 flex flex-col gap-1">
                  {entry.todos_json.map((todo, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-2"
                      style={{ fontSize: 12 }}
                    >
                      <span
                        style={{
                          width: 14,
                          height: 14,
                          borderRadius: 3,
                          border: `1px solid ${todo.done ? "var(--state-done)" : "var(--border)"}`,
                          backgroundColor: todo.done
                            ? "rgba(39,174,96,0.15)"
                            : "transparent",
                          display: "inline-flex",
                          alignItems: "center",
                          justifyContent: "center",
                          fontSize: 9,
                          color: "var(--state-done)",
                          flexShrink: 0,
                        }}
                      >
                        {todo.done ? "✓" : ""}
                      </span>
                      <span
                        style={{
                          color: todo.done
                            ? "var(--text-secondary)"
                            : "var(--text-primary)",
                          textDecoration: todo.done ? "line-through" : "none",
                        }}
                      >
                        {todo.text}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* Token info */}
              {entry.tokens_used != null && (
                <div
                  className="mt-1 flex items-center gap-3"
                  style={{ fontSize: 10, color: "var(--text-secondary)" }}
                >
                  <span>tokens: {entry.tokens_used.toLocaleString()}</span>
                  <span>total: {currentTotal.toLocaleString()}</span>
                </div>
              )}
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
