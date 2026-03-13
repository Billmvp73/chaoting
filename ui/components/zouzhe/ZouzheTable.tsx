"use client";

import { StateBadge } from "@/components/shared/StateBadge";
import type { ZouzheListItem } from "@/lib/types";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

function relativeTime(ts: string): string {
  try {
    const d = new Date(ts.endsWith("Z") ? ts : ts + "Z");
    const now = Date.now();
    const diff = now - d.getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  } catch {
    return ts;
  }
}

function truncate(s: string | null | undefined, max: number): string {
  if (!s) return "—";
  return s.length > max ? s.slice(0, max) + "..." : s;
}

const PRIORITY_COLORS: Record<string, { bg: string; text: string }> = {
  urgent: { bg: "rgba(231,76,60,0.15)", text: "#e74c3c" },
  high: { bg: "rgba(230,126,34,0.15)", text: "#e67e22" },
  normal: { bg: "rgba(138,147,158,0.15)", text: "#8a939e" },
};

const columnHelper = createColumnHelper<ZouzheListItem>();

const columns = [
  columnHelper.accessor("id", {
    header: "ID",
    cell: (info) => (
      <span
        className="font-mono"
        style={{ color: "var(--imperial-gold)", fontSize: 12 }}
      >
        {info.getValue()}
      </span>
    ),
  }),
  columnHelper.accessor("title", {
    header: "Title",
    cell: (info) => (
      <span
        style={{
          color: "var(--text-primary)",
          fontSize: 13,
          maxWidth: 400,
          display: "inline-block",
        }}
        title={info.getValue()}
      >
        {truncate(info.getValue(), 60)}
      </span>
    ),
  }),
  columnHelper.accessor("state", {
    header: "State",
    cell: (info) => <StateBadge state={info.getValue()} />,
  }),
  columnHelper.accessor("priority", {
    header: "Priority",
    cell: (info) => {
      const p = info.getValue();
      const c = PRIORITY_COLORS[p] || PRIORITY_COLORS.normal;
      return (
        <span
          style={{
            fontSize: 11,
            padding: "2px 8px",
            borderRadius: 4,
            backgroundColor: c.bg,
            color: c.text,
          }}
        >
          {p}
        </span>
      );
    },
  }),
  columnHelper.accessor("assigned_agent", {
    header: "Agent",
    cell: (info) => (
      <span style={{ color: "var(--text-secondary)", fontSize: 12 }}>
        {info.getValue() || "—"}
      </span>
    ),
  }),
  columnHelper.accessor("created_at", {
    header: "Created",
    cell: (info) => (
      <span style={{ color: "var(--text-secondary)", fontSize: 12 }}>
        {relativeTime(info.getValue())}
      </span>
    ),
  }),
  columnHelper.accessor("latest_zoubao", {
    header: "Latest Progress",
    cell: (info) => (
      <span
        style={{
          color: "var(--text-secondary)",
          fontSize: 12,
          maxWidth: 250,
          display: "inline-block",
        }}
        title={info.getValue() || undefined}
      >
        {truncate(info.getValue(), 40)}
      </span>
    ),
  }),
];

interface ZouzheTableProps {
  data: ZouzheListItem[];
  onRowClick: (id: string) => void;
}

export function ZouzheTable({ data, onRowClick }: ZouzheTableProps) {
  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <Table>
      <TableHeader>
        {table.getHeaderGroups().map((headerGroup) => (
          <TableRow
            key={headerGroup.id}
            style={{ borderColor: "var(--border)" }}
          >
            {headerGroup.headers.map((header) => (
              <TableHead
                key={header.id}
                style={{ color: "var(--text-secondary)", fontSize: 11 }}
              >
                {header.isPlaceholder
                  ? null
                  : flexRender(
                      header.column.columnDef.header,
                      header.getContext()
                    )}
              </TableHead>
            ))}
          </TableRow>
        ))}
      </TableHeader>
      <TableBody>
        {table.getRowModel().rows.length === 0 ? (
          <TableRow>
            <TableCell
              colSpan={columns.length}
              style={{
                textAlign: "center",
                color: "var(--text-secondary)",
                padding: "32px 0",
              }}
            >
              No tasks found
            </TableCell>
          </TableRow>
        ) : (
          table.getRowModel().rows.map((row) => (
            <TableRow
              key={row.id}
              onClick={() => onRowClick(row.original.id)}
              style={{
                cursor: "pointer",
                borderColor: "var(--border)",
              }}
              className="hover:bg-[var(--surface-2)]"
            >
              {row.getVisibleCells().map((cell) => (
                <TableCell key={cell.id}>
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </TableCell>
              ))}
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  );
}
