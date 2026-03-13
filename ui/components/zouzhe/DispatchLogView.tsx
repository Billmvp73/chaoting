"use client";

import { fetchDispatchLog } from "@/lib/api";
import { Copy, Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

interface DispatchLogViewProps {
  zouzheId: string;
  assignedAgent: string | null;
}

export function DispatchLogView({
  zouzheId,
  assignedAgent,
}: DispatchLogViewProps) {
  const [agentId, setAgentId] = useState(assignedAgent || "");
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadLog = useCallback(async () => {
    if (!agentId) return;
    setLoading(true);
    setError(null);
    try {
      const result = await fetchDispatchLog(zouzheId, agentId);
      setContent(result.content);
      if (!result.content) {
        setError("No log found");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load log");
      setContent(null);
    } finally {
      setLoading(false);
    }
  }, [zouzheId, agentId]);

  useEffect(() => {
    loadLog();
  }, [loadLog]);

  function handleCopy() {
    if (content) {
      navigator.clipboard.writeText(content);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Agent selector */}
      <div className="flex items-center gap-3">
        <label
          style={{ fontSize: 12, color: "var(--text-secondary)" }}
        >
          Agent:
        </label>
        <input
          type="text"
          value={agentId}
          onChange={(e) => setAgentId(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") loadLog();
          }}
          placeholder="Enter agent ID"
          style={{
            fontSize: 12,
            padding: "4px 8px",
            borderRadius: 4,
            border: "1px solid var(--border)",
            backgroundColor: "var(--surface)",
            color: "var(--text-primary)",
            flex: 1,
            maxWidth: 250,
          }}
        />
        <button
          onClick={loadLog}
          style={{
            fontSize: 11,
            padding: "4px 12px",
            borderRadius: 4,
            border: "1px solid var(--border)",
            backgroundColor: "var(--surface-2)",
            color: "var(--text-primary)",
            cursor: "pointer",
          }}
        >
          Load
        </button>
      </div>

      {/* Log content */}
      <div className="relative">
        {loading && (
          <div
            className="flex items-center justify-center"
            style={{ padding: "32px 0" }}
          >
            <Loader2
              size={20}
              className="animate-spin"
              style={{ color: "var(--text-secondary)" }}
            />
          </div>
        )}

        {!loading && error && (
          <div
            style={{
              color: "var(--text-secondary)",
              fontSize: 13,
              textAlign: "center",
              padding: "32px 0",
            }}
          >
            {error}
          </div>
        )}

        {!loading && content && (
          <>
            <button
              onClick={handleCopy}
              className="absolute top-2 right-2"
              style={{
                padding: "4px 8px",
                borderRadius: 4,
                border: "1px solid var(--border)",
                backgroundColor: "var(--surface)",
                color: "var(--text-secondary)",
                cursor: "pointer",
                fontSize: 11,
                display: "flex",
                alignItems: "center",
                gap: 4,
              }}
            >
              <Copy size={12} />
              Copy
            </button>
            <pre
              className="font-mono"
              style={{
                fontSize: 11,
                lineHeight: 1.5,
                padding: 16,
                backgroundColor: "var(--background)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                overflow: "auto",
                maxHeight: 600,
                color: "var(--text-primary)",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {content}
            </pre>
          </>
        )}
      </div>
    </div>
  );
}
