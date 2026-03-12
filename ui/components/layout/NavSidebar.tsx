"use client";

import { useChaotingStore } from "@/lib/store";
import { BarChart3, LayoutDashboard, Users } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/zouzhe", label: "Tasks", icon: BarChart3 },
  { href: "/agents", label: "Agents", icon: Users },
];

export function NavSidebar() {
  const pathname = usePathname();
  const sseConnected = useChaotingStore((s) => s.sseConnected);

  return (
    <aside
      className="fixed left-0 top-0 bottom-0 flex flex-col justify-between"
      style={{
        width: 220,
        backgroundColor: "var(--surface)",
        borderRight: "1px solid var(--border)",
      }}
    >
      <div>
        {/* Brand */}
        <div className="px-6 py-6">
          <h1
            className="text-2xl font-bold tracking-wide"
            style={{ color: "var(--primary)" }}
          >
            朝廷
          </h1>
          <p
            className="text-xs mt-1"
            style={{ color: "var(--text-secondary)" }}
          >
            Task Orchestration
          </p>
        </div>

        {/* Navigation */}
        <nav className="px-3 space-y-1">
          {NAV_ITEMS.map((item) => {
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className="flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-colors"
                style={{
                  backgroundColor: isActive
                    ? "var(--surface-2)"
                    : "transparent",
                  color: isActive
                    ? "var(--text-accent)"
                    : "var(--text-secondary)",
                }}
              >
                <item.icon size={18} />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>

      {/* SSE status */}
      <div
        className="px-6 py-4 flex items-center gap-2 text-xs"
        style={{ color: "var(--text-secondary)" }}
      >
        <span
          className="inline-block w-2 h-2 rounded-full"
          style={{
            backgroundColor: sseConnected
              ? "var(--state-done)"
              : "var(--state-failed)",
          }}
        />
        {sseConnected ? "Connected" : "Disconnected"}
      </div>
    </aside>
  );
}
