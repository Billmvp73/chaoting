"use client";

import { Card, CardContent } from "@/components/ui/card";
import type { AgentStatus } from "@/lib/types";

const STATUS_STYLES: Record<
  string,
  { label: string; color: string }
> = {
  executing: { label: "执行中", color: "var(--state-executing)" },
  recent: { label: "近期活跃", color: "var(--state-planning)" },
  idle: { label: "闲置", color: "var(--text-secondary)" },
};

export function AgentStatusPanel({
  agents,
}: {
  agents: AgentStatus[];
}) {
  if (agents.length === 0) {
    return (
      <div
        className="text-center py-8 text-sm"
        style={{ color: "var(--text-secondary)" }}
      >
        暂无 Agent 信息
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {agents.map((agent) => {
        const style = STATUS_STYLES[agent.status] || STATUS_STYLES.idle;
        return (
          <Card
            key={agent.agent_id}
            className="border"
            style={{
              backgroundColor: "var(--surface)",
              borderColor: "var(--border)",
            }}
          >
            <CardContent className="p-4">
              <div className="flex items-center justify-between mb-2">
                <span
                  className="font-mono text-sm font-medium"
                  style={{ color: "var(--text-primary)" }}
                >
                  {agent.agent_id}
                </span>
                <div className="flex items-center gap-1.5">
                  <span
                    className="w-2 h-2 rounded-full"
                    style={{ backgroundColor: style.color }}
                  />
                  <span
                    className="text-xs"
                    style={{ color: style.color }}
                  >
                    {style.label}
                  </span>
                </div>
              </div>
              {agent.active_zouzhe_title && (
                <div
                  className="text-xs mt-1 truncate"
                  style={{ color: "var(--text-secondary)" }}
                >
                  <span style={{ color: "var(--text-accent)" }}>
                    {agent.active_zouzhe_id}
                  </span>{" "}
                  {agent.active_zouzhe_title}
                </div>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
