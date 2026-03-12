"use client";

import { StatusBadge } from "@/components/shared/StatusBadge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { ZouzheListItem } from "@/lib/types";

function formatTime(ts: string | null): string {
  if (!ts) return "—";
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

export function ActiveZouzheList({
  items,
}: {
  items: ZouzheListItem[];
}) {
  if (items.length === 0) {
    return (
      <div
        className="text-center py-8 text-sm"
        style={{ color: "var(--text-secondary)" }}
      >
        暂无活跃任务
      </div>
    );
  }

  return (
    <div className="overflow-auto">
      <Table>
        <TableHeader>
          <TableRow style={{ borderColor: "var(--border)" }}>
            <TableHead
              className="text-xs"
              style={{ color: "var(--text-secondary)" }}
            >
              ID
            </TableHead>
            <TableHead
              className="text-xs"
              style={{ color: "var(--text-secondary)" }}
            >
              Title
            </TableHead>
            <TableHead
              className="text-xs"
              style={{ color: "var(--text-secondary)" }}
            >
              State
            </TableHead>
            <TableHead
              className="text-xs"
              style={{ color: "var(--text-secondary)" }}
            >
              Agent
            </TableHead>
            <TableHead
              className="text-xs"
              style={{ color: "var(--text-secondary)" }}
            >
              Updated
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((z) => (
            <TableRow
              key={z.id}
              style={{ borderColor: "var(--border)" }}
            >
              <TableCell
                className="font-mono text-xs"
                style={{ color: "var(--text-accent)" }}
              >
                {z.id}
              </TableCell>
              <TableCell
                className="text-sm max-w-[300px] truncate"
                style={{ color: "var(--text-primary)" }}
              >
                {z.title}
              </TableCell>
              <TableCell>
                <StatusBadge state={z.state} />
              </TableCell>
              <TableCell
                className="text-xs"
                style={{ color: "var(--text-secondary)" }}
              >
                {z.assigned_agent || "—"}
              </TableCell>
              <TableCell
                className="text-xs"
                style={{ color: "var(--text-secondary)" }}
              >
                {formatTime(z.updated_at)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
