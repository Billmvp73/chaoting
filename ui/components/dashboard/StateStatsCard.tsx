"use client";

import { Card, CardContent } from "@/components/ui/card";
import type { ZouzheState } from "@/lib/types";

const STATE_META: Record<
  string,
  { label: string; color: string }
> = {
  created: { label: "待分配", color: "var(--state-created)" },
  planning: { label: "规划中", color: "var(--state-planning)" },
  reviewing: { label: "审核中", color: "var(--state-reviewing)" },
  executing: { label: "执行中", color: "var(--state-executing)" },
  done: { label: "完成", color: "var(--state-done)" },
  failed: { label: "失败", color: "var(--state-failed)" },
  escalated: { label: "上呈", color: "var(--state-escalated)" },
  timeout: { label: "超时", color: "var(--state-timeout)" },
};

const ALL_STATES: ZouzheState[] = [
  "created",
  "planning",
  "reviewing",
  "executing",
  "done",
  "failed",
  "escalated",
  "timeout",
];

export function StateStatsCards({
  stats,
}: {
  stats: Record<string, number>;
}) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-8 gap-3">
      {ALL_STATES.map((state) => {
        const meta = STATE_META[state];
        const count = stats[state] || 0;
        return (
          <Card
            key={state}
            className="border"
            style={{
              backgroundColor: "var(--surface)",
              borderColor: "var(--border)",
            }}
          >
            <CardContent className="p-4">
              <div className="flex items-center gap-2 mb-2">
                <span
                  className="w-2.5 h-2.5 rounded-full"
                  style={{ backgroundColor: meta.color }}
                />
                <span
                  className="text-xs"
                  style={{ color: "var(--text-secondary)" }}
                >
                  {meta.label}
                </span>
              </div>
              <div
                className="text-2xl font-bold"
                style={{ color: meta.color }}
              >
                {count}
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
