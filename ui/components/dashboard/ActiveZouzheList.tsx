"use client";

import { StateBadge } from "@/components/shared/StateBadge";
import type { ZouzheListItem } from "@/lib/types";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";

const DEPT_EMOJI: Record<string, string> = {
  bingbu: "⚔️",
  gongbu: "🔧",
  hubu: "💰",
  zhongshu: "📜",
  menxia: "🏛",
  libu: "🌿",
  xingbu: "⚖️",
  silijian: "🎯",
};

function getDeptEmoji(agent: string | null | undefined): string {
  if (!agent) return "○";
  for (const [key, emoji] of Object.entries(DEPT_EMOJI)) {
    if (agent.toLowerCase().includes(key)) return emoji;
  }
  return "○";
}

function formatTime(ts: string | null | undefined): string {
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

function ZouzheCard({
  item,
  index,
}: {
  item: ZouzheListItem;
  index: number;
}) {
  const isExecuting = item.state === "executing";
  const prevItemStr = useRef(JSON.stringify(item));
  const [shimmer, setShimmer] = useState(false);

  useEffect(() => {
    const current = JSON.stringify(item);
    if (current !== prevItemStr.current) {
      setShimmer(true);
      const t = setTimeout(() => setShimmer(false), 800);
      prevItemStr.current = current;
      return () => clearTimeout(t);
    }
  }, [item]);

  const stateColor = `var(--state-${item.state})`;

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      transition={{ delay: index * 0.05, duration: 0.3 }}
      className={isExecuting ? "executing-glow-border" : ""}
      style={{
        position: "relative",
        backgroundColor: "var(--surface)",
        border: "1px solid var(--border)",
        borderLeftWidth: 4,
        borderLeftStyle: "solid",
        borderLeftColor: isExecuting ? undefined : stateColor,
        borderRadius: "0 8px 8px 0",
        padding: "12px 16px",
        marginBottom: 8,
        overflow: "hidden",
      }}
    >
      {shimmer && (
        <div
          className="shimmer-gold"
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            pointerEvents: "none",
            zIndex: 1,
          }}
        />
      )}

      <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
        {/* ZZ-ID 印章 stamp */}
        <div
          style={{
            fontFamily: "'Noto Serif SC', Georgia, serif",
            fontSize: 9,
            color: "#c0392b",
            backgroundColor: "rgba(192, 57, 43, 0.1)",
            border: "1px solid rgba(192, 57, 43, 0.3)",
            borderRadius: 999,
            padding: "2px 8px",
            letterSpacing: "0.06em",
            whiteSpace: "nowrap",
            flexShrink: 0,
            marginTop: 2,
          }}
        >
          {item.id.replace("ZZ-", "")}
        </div>
        <div
          style={{
            flex: 1,
            fontSize: 13,
            color: "var(--text-primary)",
            lineHeight: 1.4,
            fontWeight: 500,
          }}
        >
          {item.title}
        </div>
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginTop: 8,
          flexWrap: "wrap",
        }}
      >
        <StateBadge state={item.state} />
        <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>
          {getDeptEmoji(item.assigned_agent)}
          {item.assigned_agent ? ` ${item.assigned_agent}` : " —"}
        </span>
        <span
          style={{
            fontSize: 10,
            color: "var(--text-secondary)",
            marginLeft: "auto",
          }}
        >
          {formatTime(item.updated_at)}
        </span>
      </div>
    </motion.div>
  );
}

export function ActiveZouzheList({ items }: { items: ZouzheListItem[] }) {
  if (items.length === 0) {
    return (
      <div
        style={{
          textAlign: "center",
          padding: "32px 0",
          fontSize: 13,
          color: "var(--text-secondary)",
          fontFamily: "'Noto Serif SC', Georgia, serif",
        }}
      >
        「暂无活跃任务」
      </div>
    );
  }

  return (
    <AnimatePresence>
      {items.map((item, i) => (
        <ZouzheCard key={item.id} item={item} index={i} />
      ))}
    </AnimatePresence>
  );
}
