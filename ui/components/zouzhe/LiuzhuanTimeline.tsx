"use client";

import type { LiuzhuanEntry } from "@/lib/types";

const ACTION_COLORS: Record<string, { bg: string; text: string }> = {
  dispatch: { bg: "rgba(100,149,237,0.15)", text: "#6495ed" },
  approve: { bg: "rgba(39,174,96,0.15)", text: "#27ae60" },
  reject: { bg: "rgba(231,76,60,0.15)", text: "#e74c3c" },
  fail: { bg: "rgba(231,76,60,0.15)", text: "#e74c3c" },
  submit_review: { bg: "rgba(155,89,182,0.15)", text: "#9b59b6" },
};

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

interface LiuzhuanTimelineProps {
  entries: LiuzhuanEntry[];
}

export function LiuzhuanTimeline({ entries }: LiuzhuanTimelineProps) {
  if (entries.length === 0) {
    return (
      <div style={{ color: "var(--text-secondary)", fontSize: 13 }}>
        No transfer history
      </div>
    );
  }

  // Group by timestamp to detect parallel branches
  const grouped: Map<string, LiuzhuanEntry[]> = new Map();
  for (const entry of entries) {
    const key = entry.timestamp;
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key)!.push(entry);
  }

  return (
    <div className="flex flex-col gap-0">
      {entries.map((entry, index) => {
        const sameTimestamp =
          index > 0 && entries[index - 1].timestamp === entry.timestamp;
        const actionColor =
          ACTION_COLORS[entry.action] || {
            bg: "rgba(138,147,158,0.15)",
            text: "#8a939e",
          };

        return (
          <div
            key={entry.id}
            className="flex items-start gap-3 relative"
            style={{ paddingLeft: sameTimestamp ? 24 : 0 }}
          >
            {/* Vertical line */}
            {index < entries.length - 1 && (
              <div
                style={{
                  position: "absolute",
                  left: sameTimestamp ? 33 : 9,
                  top: 20,
                  bottom: -4,
                  width: 1,
                  backgroundColor: "var(--border)",
                }}
              />
            )}

            {/* Dot */}
            <div
              className="flex-shrink-0 mt-1.5"
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                backgroundColor: actionColor.text,
                marginTop: 6,
              }}
            />

            {/* Content */}
            <div className="pb-4 flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span
                  className="font-mono"
                  style={{ fontSize: 11, color: "var(--text-secondary)" }}
                >
                  {formatTimestamp(entry.timestamp)}
                </span>

                <span style={{ fontSize: 12, color: "var(--text-primary)" }}>
                  {entry.from_role || "—"}
                  <span style={{ color: "var(--text-secondary)", margin: "0 4px" }}>
                    →
                  </span>
                  {entry.to_role || "—"}
                </span>

                <span
                  style={{
                    fontSize: 10,
                    padding: "1px 6px",
                    borderRadius: 3,
                    backgroundColor: actionColor.bg,
                    color: actionColor.text,
                  }}
                >
                  {entry.action}
                </span>
              </div>

              {entry.remark && (
                <div
                  style={{
                    fontSize: 11,
                    color: "var(--text-secondary)",
                    marginTop: 2,
                  }}
                >
                  {entry.remark}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
