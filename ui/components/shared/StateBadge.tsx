"use client";

import type { ZouzheState } from "@/lib/types";
import { AnimatePresence, motion } from "framer-motion";

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
  done: "已完成",
  failed: "已失败",
  escalated: "已上呈",
  timeout: "已超时",
};

export function StateBadge({ state }: { state: ZouzheState }) {
  const color = STATE_COLORS[state] ?? "var(--text-secondary)";
  return (
    <AnimatePresence mode="wait">
      <motion.span
        key={state}
        initial={{ clipPath: "inset(0 100% 0 0)" }}
        animate={{ clipPath: "inset(0 0% 0 0)" }}
        exit={{ clipPath: "inset(0 0 0 100%)" }}
        transition={{ duration: 0.25, ease: "easeInOut" }}
        style={{
          display: "inline-block",
          fontFamily: "'Noto Serif SC', Georgia, serif",
          fontSize: 10,
          padding: "2px 7px",
          borderRadius: 4,
          border: `1px solid ${color}55`,
          color: color,
          letterSpacing: "0.03em",
          backgroundColor: `${color}1a`,
        }}
      >
        「{STATE_LABELS[state] ?? state}」
      </motion.span>
    </AnimatePresence>
  );
}
