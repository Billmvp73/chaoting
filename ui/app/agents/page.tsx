"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function AgentsPage() {
  return (
    <div className="p-6">
      <h2
        className="text-xl font-bold mb-4"
        style={{ color: "var(--text-primary)" }}
      >
        Agents
      </h2>
      <Card
        className="border"
        style={{
          backgroundColor: "var(--surface)",
          borderColor: "var(--border)",
        }}
      >
        <CardHeader>
          <CardTitle
            className="text-sm"
            style={{ color: "var(--text-secondary)" }}
          >
            Agent 管理
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p
            className="text-sm"
            style={{ color: "var(--text-secondary)" }}
          >
            Agent 详细状态与历史页面 — Phase 2 实现
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
