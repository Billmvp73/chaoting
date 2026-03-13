"use client";

import type { ToupiaoEntry } from "@/lib/types";

const VOTE_COLORS: Record<string, { bg: string; text: string }> = {
  approve: { bg: "rgba(39,174,96,0.15)", text: "#27ae60" },
  reject: { bg: "rgba(231,76,60,0.15)", text: "#e74c3c" },
  revise: { bg: "rgba(241,196,15,0.15)", text: "#f1c40f" },
};

function formatTimestamp(ts: string): string {
  try {
    const d = new Date(ts.endsWith("Z") ? ts : ts + "Z");
    return d.toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return ts;
  }
}

interface ToupiaoPanelProps {
  entries: ToupiaoEntry[];
}

export function ToupiaoPanel({ entries }: ToupiaoPanelProps) {
  if (entries.length === 0) {
    return (
      <div style={{ color: "var(--text-secondary)", fontSize: 13 }}>
        No review votes
      </div>
    );
  }

  // Count votes and rounds
  const voteCounts: Record<string, number> = {};
  const rounds = new Set<string>();
  for (const e of entries) {
    voteCounts[e.vote] = (voteCounts[e.vote] || 0) + 1;
    // Infer round from the entry if there's a round field, otherwise count unique timestamps
  }
  // Count distinct rounds by looking at unique (jishi_id sets per timestamp group)
  // Simple heuristic: count distinct timestamps as rounds
  for (const e of entries) {
    rounds.add(e.timestamp.slice(0, 16)); // group by minute
  }

  return (
    <div>
      {/* Grid of vote cards */}
      <div
        className="grid gap-3"
        style={{ gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))" }}
      >
        {entries.map((entry) => {
          const vc =
            VOTE_COLORS[entry.vote] || {
              bg: "rgba(138,147,158,0.15)",
              text: "#8a939e",
            };
          return (
            <div
              key={entry.id}
              style={{
                backgroundColor: "var(--surface-2)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                padding: "12px 14px",
              }}
            >
              <div className="flex items-center justify-between mb-2">
                <span
                  style={{
                    fontSize: 13,
                    color: "var(--text-primary)",
                    fontWeight: 500,
                  }}
                >
                  {entry.jishi_id}
                </span>
                <span
                  style={{
                    fontSize: 10,
                    padding: "2px 8px",
                    borderRadius: 3,
                    backgroundColor: vc.bg,
                    color: vc.text,
                    fontWeight: 600,
                  }}
                >
                  {entry.vote}
                </span>
              </div>

              <div
                style={{
                  fontSize: 11,
                  color: "var(--text-secondary)",
                  marginBottom: 6,
                }}
              >
                {entry.agent_id}
              </div>

              {entry.reason && (
                <div
                  style={{
                    fontSize: 12,
                    color: "var(--text-primary)",
                    lineHeight: 1.4,
                    marginBottom: 6,
                  }}
                >
                  {entry.reason}
                </div>
              )}

              <div
                style={{
                  fontSize: 10,
                  color: "var(--text-secondary)",
                  textAlign: "right",
                }}
              >
                {formatTimestamp(entry.timestamp)}
              </div>
            </div>
          );
        })}
      </div>

      {/* Summary bar */}
      <div
        className="mt-4 flex items-center gap-4"
        style={{
          padding: "8px 12px",
          backgroundColor: "var(--surface-2)",
          borderRadius: 4,
          fontSize: 12,
          color: "var(--text-secondary)",
        }}
      >
        <span style={{ color: "#27ae60" }}>
          {voteCounts["approve"] || 0} approve
        </span>
        <span style={{ color: "#e74c3c" }}>
          {voteCounts["reject"] || 0} reject
        </span>
        <span style={{ color: "#f1c40f" }}>
          {voteCounts["revise"] || 0} revise
        </span>
        <span style={{ marginLeft: "auto" }}>
          {rounds.size} round{rounds.size !== 1 ? "s" : ""}
        </span>
      </div>
    </div>
  );
}
