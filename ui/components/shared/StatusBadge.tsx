"use client";

import { Badge } from "@/components/ui/badge";
import type { ZouzheState } from "@/lib/types";

const STATE_COLORS: Record<ZouzheState, string> = {
  created: "var(--state-created)",
  planning: "var(--state-planning)",
  reviewing: "var(--state-reviewing)",
  executing: "var(--state-executing)",
  done: "var(--state-done)",
  failed: "var(--state-failed)",
  escalated: "var(--state-escalated)",
  timeout: "var(--state-timeout)",
};

const STATE_LABELS: Record<ZouzheState, string> = {
  created: "待分配",
  planning: "规划中",
  reviewing: "审核中",
  executing: "执行中",
  done: "完成",
  failed: "失败",
  escalated: "上呈",
  timeout: "超时",
};

export function StatusBadge({ state }: { state: ZouzheState }) {
  const color = STATE_COLORS[state] || "var(--text-secondary)";
  return (
    <Badge
      variant="outline"
      className="text-xs font-medium px-2 py-0.5"
      style={{
        borderColor: color,
        color: color,
        backgroundColor: `color-mix(in srgb, ${color} 15%, transparent)`,
      }}
    >
      {STATE_LABELS[state] || state}
    </Badge>
  );
}
