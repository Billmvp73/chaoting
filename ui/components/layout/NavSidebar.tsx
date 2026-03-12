"use client";

import { useChaotingStore } from "@/lib/store";
import { BarChart3, LayoutDashboard, Users } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const NAV_ITEMS = [
  { href: "/dashboard", label: "仪表盘", icon: LayoutDashboard },
  { href: "/zouzhe", label: "任务列表", icon: BarChart3 },
  { href: "/agents", label: "部门状态", icon: Users },
];

const VERSION = "v0.3.0";

export function NavSidebar() {
  const pathname = usePathname();
  const sseConnected = useChaotingStore((s) => s.sseConnected);
  const [currentTime, setCurrentTime] = useState("");

  useEffect(() => {
    const update = () =>
      setCurrentTime(
        new Date().toLocaleTimeString("zh-CN", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        })
      );
    update();
    const timer = setInterval(update, 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <aside
      className="fixed left-0 top-0 bottom-0 flex flex-col justify-between"
      style={{
        width: 240,
        backgroundColor: "var(--surface)",
        borderRight: "1px solid var(--border)",
      }}
    >
      <div>
        {/* Brand */}
        <div className="px-6 pt-7 pb-4">
          <h1
            style={{
              fontFamily: "'Noto Serif SC', Georgia, serif",
              fontSize: "1.875rem",
              fontWeight: 900,
              color: "var(--imperial-gold)",
              letterSpacing: "0.1em",
              lineHeight: 1,
            }}
          >
            朝廷
          </h1>
          {/* ○ ◆ ○ decorative subtitle */}
          <div
            className="mt-2 flex items-center gap-1.5"
            style={{ color: "var(--text-secondary)", fontSize: 10 }}
          >
            <span style={{ color: "var(--imperial-gold)", opacity: 0.4 }}>○</span>
            <span style={{ letterSpacing: "0.12em" }}>TASK ORCHESTRATION</span>
            <span style={{ color: "var(--imperial-gold)", opacity: 0.4 }}>○</span>
          </div>
        </div>

        {/* ─ ○ 御 ○ ─ decorative section divider */}
        <div
          className="mx-6 mb-5 flex items-center gap-2"
          style={{ color: "var(--border)", fontSize: 9 }}
        >
          <span
            style={{
              flex: 1,
              height: 1,
              background: "linear-gradient(90deg, var(--imperial-gold), var(--border))",
              display: "block",
            }}
          />
          <span
            style={{
              fontFamily: "'Noto Serif SC', Georgia, serif",
              color: "var(--imperial-gold)",
              opacity: 0.5,
              fontSize: 9,
              letterSpacing: "0.15em",
            }}
          >
            ○ 御 ○
          </span>
          <span
            style={{
              flex: 1,
              height: 1,
              background: "linear-gradient(90deg, var(--border), transparent)",
              display: "block",
            }}
          />
        </div>

        {/* Navigation */}
        <nav className="px-3 space-y-0.5">
          {NAV_ITEMS.map((item) => {
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className="flex items-center gap-3 px-3 py-2.5 rounded-sm text-sm transition-colors"
                style={{
                  backgroundColor: "transparent",
                  color: isActive ? "var(--imperial-gold)" : "rgba(212,160,23,0.4)",
                  borderLeft: isActive
                    ? "3px solid var(--imperial-gold)"
                    : "3px solid transparent",
                  paddingLeft: isActive ? "10px" : "10px",
                }}
              >
                <item.icon size={16} style={{ opacity: isActive ? 1 : 0.5 }} />
                <span style={{ fontWeight: isActive ? 600 : 400 }}>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        {/* ─ ○ 导 ○ ─ section divider */}
        <div
          className="mx-6 my-5 flex items-center gap-2"
          style={{ color: "var(--border)", fontSize: 9 }}
        >
          <span
            style={{
              flex: 1,
              height: 1,
              background: "var(--border)",
              display: "block",
            }}
          />
          <span
            style={{
              fontFamily: "'Noto Serif SC', Georgia, serif",
              color: "var(--text-secondary)",
              opacity: 0.4,
              fontSize: 9,
              letterSpacing: "0.15em",
            }}
          >
            ─ ◆ ─
          </span>
          <span
            style={{
              flex: 1,
              height: 1,
              background: "var(--border)",
              display: "block",
            }}
          />
        </div>
      </div>

      {/* Footer: SSE status + time + version */}
      <div
        className="px-5 py-4 space-y-2"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        {/* SSE status */}
        <div className="flex items-center gap-2 text-xs">
          <span
            className="inline-block w-2 h-2 rounded-full flex-shrink-0"
            style={{
              backgroundColor: sseConnected ? "#27ae60" : "var(--cinnabar-red)",
              boxShadow: sseConnected
                ? "0 0 4px rgba(39,174,96,0.6)"
                : "0 0 4px rgba(192,57,43,0.6)",
            }}
          />
          <span
            style={{
              fontFamily: "'Noto Serif SC', Georgia, serif",
              fontSize: 10,
              color: sseConnected ? "#27ae60" : "var(--cinnabar-red)",
              letterSpacing: "0.04em",
            }}
          >
            {sseConnected ? "「御线畅通」" : "「御线中断」"}
          </span>
        </div>

        {/* Clock + Version */}
        <div
          className="flex items-center justify-between"
          style={{ color: "var(--text-secondary)", fontSize: 9, opacity: 0.5 }}
        >
          <span className="font-mono">{currentTime}</span>
          <span style={{ letterSpacing: "0.04em" }}>{VERSION}</span>
        </div>
      </div>
    </aside>
  );
}
