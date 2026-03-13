"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function ZouzhePage() {
  return (
    <div className="p-6">
      <h2
        className="text-xl font-bold mb-4"
        style={{ color: "var(--text-primary)" }}
      >
        Tasks
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
            奏折列表
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p
            className="text-sm"
            style={{ color: "var(--text-secondary)" }}
          >
            详细任务列表页面 — Phase 2 实现
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
