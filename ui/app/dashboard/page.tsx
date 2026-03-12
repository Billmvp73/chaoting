"use client";

import { AgentStatusPanel } from "@/components/dashboard/AgentStatusPanel";
import { ActiveZouzheList } from "@/components/dashboard/ActiveZouzheList";
import { StateStatsCards } from "@/components/dashboard/StateStatsCard";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchAgents, fetchStateStats, fetchZouzheList } from "@/lib/api";
import { useChaotingStore } from "@/lib/store";
import type { ZouzheListItem } from "@/lib/types";
import { useEffect, useState } from "react";

const ACTIVE_STATES = ["executing", "planning", "reviewing", "escalated"];

export default function DashboardPage() {
  const { stateStats, setStateStats, agentStatuses, setAgentStatuses } =
    useChaotingStore();
  const zouzheList = useChaotingStore((s) => s.zouzheList);
  const setZouzheList = useChaotingStore((s) => s.setZouzheList);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [stats, zouzhe, agents] = await Promise.all([
          fetchStateStats(),
          fetchZouzheList({ limit: 100 }),
          fetchAgents(),
        ]);
        if (cancelled) return;
        setStateStats(stats);
        setZouzheList(zouzhe);
        setAgentStatuses(agents);
      } catch {
        // API not available yet — leave empty
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    // Refresh every 30s as a fallback beyond SSE
    const interval = setInterval(load, 30000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [setStateStats, setZouzheList, setAgentStatuses]);

  // Filter active tasks from the store (SSE-updated)
  const activeTasks: ZouzheListItem[] = zouzheList
    .filter((z) => ACTIVE_STATES.includes(z.state))
    .sort((a, b) => {
      // Priority sort then updated_at desc
      const pa = a.priority === "high" ? 0 : a.priority === "normal" ? 1 : 2;
      const pb = b.priority === "high" ? 0 : b.priority === "normal" ? 1 : 2;
      if (pa !== pb) return pa - pb;
      return (b.updated_at || "").localeCompare(a.updated_at || "");
    });

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h2
          className="text-xl font-bold"
          style={{ color: "var(--text-primary)" }}
        >
          Dashboard
        </h2>
        <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
          朝廷任务编排系统 — 实时监控面板
        </p>
      </div>

      {/* State stats */}
      <section>
        <h3
          className="text-sm font-medium mb-3"
          style={{ color: "var(--text-secondary)" }}
        >
          奏折状态概览
        </h3>
        <StateStatsCards stats={stateStats} />
      </section>

      {/* Active tasks */}
      <section>
        <Card
          className="border"
          style={{
            backgroundColor: "var(--surface)",
            borderColor: "var(--border)",
          }}
        >
          <CardHeader className="pb-3">
            <CardTitle
              className="text-sm font-medium"
              style={{ color: "var(--text-secondary)" }}
            >
              活跃任务 ({activeTasks.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div
                className="text-center py-8 text-sm"
                style={{ color: "var(--text-secondary)" }}
              >
                Loading...
              </div>
            ) : (
              <ActiveZouzheList items={activeTasks} />
            )}
          </CardContent>
        </Card>
      </section>

      {/* Agent status */}
      <section>
        <h3
          className="text-sm font-medium mb-3"
          style={{ color: "var(--text-secondary)" }}
        >
          Agent 状态
        </h3>
        {loading ? (
          <div
            className="text-center py-8 text-sm"
            style={{ color: "var(--text-secondary)" }}
          >
            Loading...
          </div>
        ) : (
          <AgentStatusPanel agents={agentStatuses} />
        )}
      </section>
    </div>
  );
}
