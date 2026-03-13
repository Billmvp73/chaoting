"use client";

import { StateBadge } from "@/components/shared/StateBadge";
import { DecideModal } from "@/components/zouzhe/DecideModal";
import { DispatchLogView } from "@/components/zouzhe/DispatchLogView";
import { LiuzhuanTimeline } from "@/components/zouzhe/LiuzhuanTimeline";
import { PlanStepsTimeline } from "@/components/zouzhe/PlanStepsTimeline";
import { ReviseModal } from "@/components/zouzhe/ReviseModal";
import { ToupiaoPanel } from "@/components/zouzhe/ToupiaoPanel";
import { ZoubaoFeed } from "@/components/zouzhe/ZoubaoFeed";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import {
  fetchLiuzhuan,
  fetchToupiao,
  fetchZoubao,
  fetchZouzheDetail,
} from "@/lib/api";
import type {
  LiuzhuanEntry,
  ToupiaoEntry,
  ZoubaoEntry,
  ZouzheDetail,
} from "@/lib/types";
import { ArrowLeft, Check, Copy } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

function formatTime(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    const d = new Date(ts.endsWith("Z") ? ts : ts + "Z");
    return d.toLocaleString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return ts;
  }
}

export default function ZouzheDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [detail, setDetail] = useState<ZouzheDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Sub-resource states
  const [liuzhuan, setLiuzhuan] = useState<LiuzhuanEntry[] | null>(null);
  const [toupiao, setToupiao] = useState<ToupiaoEntry[] | null>(null);
  const [zoubao, setZoubao] = useState<ZoubaoEntry[] | null>(null);

  // Modals
  const [showRevise, setShowRevise] = useState(false);
  const [showDecide, setShowDecide] = useState(false);

  // Copy state
  const [copied, setCopied] = useState(false);

  // Active tab for lazy loading
  const [activeTab, setActiveTab] = useState("overview");

  const loadDetail = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchZouzheDetail(id);
      setDetail(data);
      // Pre-populate sub-resources from the detail response
      if (data.liuzhuan) setLiuzhuan(data.liuzhuan);
      if (data.toupiao) setToupiao(data.toupiao);
      if (data.zoubao) setZoubao(data.zoubao);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load task");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  // Lazy load sub-resources when tab changes
  useEffect(() => {
    if (!detail) return;

    if (activeTab === "transfer" && liuzhuan === null) {
      fetchLiuzhuan(id).then(setLiuzhuan).catch(() => {});
    }
    if (activeTab === "votes" && toupiao === null) {
      fetchToupiao(id).then(setToupiao).catch(() => {});
    }
    if (activeTab === "progress" && zoubao === null) {
      fetchZoubao(id).then(setZoubao).catch(() => {});
    }
  }, [activeTab, detail, id, liuzhuan, toupiao, zoubao]);

  function handleCopyId() {
    navigator.clipboard.writeText(id);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  if (loading) {
    return (
      <div
        className="p-6"
        style={{ color: "var(--text-secondary)", fontSize: 14 }}
      >
        Loading...
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="p-6">
        <button
          onClick={() => router.push("/zouzhe")}
          className="flex items-center gap-1 mb-4"
          style={{
            fontSize: 13,
            color: "var(--text-secondary)",
            cursor: "pointer",
            background: "none",
            border: "none",
          }}
        >
          <ArrowLeft size={14} /> Tasks
        </button>
        <div style={{ color: "var(--state-failed)", fontSize: 14 }}>
          {error || "Task not found"}
        </div>
      </div>
    );
  }

  // Parse plan steps
  const planSteps: string[] = (() => {
    if (!detail.plan) return [];
    const p = detail.plan;
    if (Array.isArray(p)) return p.map((s) => String(s));
    if (typeof p === "object" && "steps" in p && Array.isArray(p.steps)) {
      return (p.steps as unknown[]).map((s) => {
        if (typeof s === "string") return s;
        if (typeof s === "object" && s !== null && "description" in s) {
          return String((s as { description: unknown }).description);
        }
        return JSON.stringify(s);
      });
    }
    return [];
  })();

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center gap-3 mb-4">
        <button
          onClick={() => router.push("/zouzhe")}
          className="flex items-center gap-1"
          style={{
            fontSize: 13,
            color: "var(--text-secondary)",
            cursor: "pointer",
            background: "none",
            border: "none",
          }}
        >
          <ArrowLeft size={14} /> Tasks
        </button>
      </div>

      <div className="flex items-center gap-3 mb-2 flex-wrap">
        <span
          className="font-mono"
          style={{
            fontSize: 16,
            color: "var(--imperial-gold)",
            fontWeight: 600,
          }}
        >
          {detail.id}
        </span>

        <StateBadge state={detail.state} />

        <button
          onClick={handleCopyId}
          style={{
            padding: "2px 6px",
            borderRadius: 3,
            border: "1px solid var(--border)",
            backgroundColor: "transparent",
            color: "var(--text-secondary)",
            cursor: "pointer",
            fontSize: 11,
            display: "flex",
            alignItems: "center",
            gap: 3,
          }}
        >
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied ? "Copied" : "Copy ID"}
        </button>

        {/* Action buttons */}
        <div id="action-buttons-placeholder" className="ml-auto flex gap-2">
          {detail.state === "done" && (
            <button
              onClick={() => setShowRevise(true)}
              style={{
                fontSize: 12,
                padding: "5px 14px",
                borderRadius: 4,
                border: "1px solid var(--state-escalated)",
                backgroundColor: "rgba(230,126,34,0.1)",
                color: "var(--state-escalated)",
                cursor: "pointer",
                fontWeight: 500,
              }}
            >
              Revise
            </button>
          )}
          {detail.state === "escalated" && (
            <button
              onClick={() => setShowDecide(true)}
              style={{
                fontSize: 12,
                padding: "5px 14px",
                borderRadius: 4,
                border: "1px solid var(--imperial-gold)",
                backgroundColor: "rgba(212,160,23,0.1)",
                color: "var(--imperial-gold)",
                cursor: "pointer",
                fontWeight: 500,
              }}
            >
              Decide
            </button>
          )}
        </div>
      </div>

      {/* Title */}
      <h2
        style={{
          fontSize: 18,
          fontWeight: 600,
          color: "var(--text-primary)",
          marginBottom: 12,
        }}
      >
        {detail.title}
      </h2>

      {/* Meta row */}
      <div
        className="flex items-center gap-4 flex-wrap mb-6"
        style={{ fontSize: 12, color: "var(--text-secondary)" }}
      >
        <span>Agent: {detail.assigned_agent || "—"}</span>
        <span>Priority: {detail.priority}</span>
        <span>Created: {formatTime(detail.created_at)}</span>
        <span>Updated: {formatTime(detail.updated_at)}</span>
        <span>Retries: {detail.retry_count}</span>
        <span>Revisions: {detail.exec_revise_count}</span>
      </div>

      {/* Tabs */}
      <Tabs
        defaultValue="overview"
        onValueChange={(v: string | number | null) => {
          if (typeof v === "string") setActiveTab(v);
        }}
      >
        <TabsList variant="line">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="transfer">Transfer History</TabsTrigger>
          <TabsTrigger value="votes">Review Votes</TabsTrigger>
          <TabsTrigger value="progress">Progress Feed</TabsTrigger>
          <TabsTrigger value="log">Dispatch Log</TabsTrigger>
        </TabsList>

        {/* Overview */}
        <TabsContent value="overview">
          <div
            className="mt-4"
            style={{
              backgroundColor: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: 20,
            }}
          >
            {/* Description */}
            <div className="mb-6">
              <h4
                style={{
                  fontSize: 12,
                  color: "var(--text-secondary)",
                  marginBottom: 8,
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                }}
              >
                Description
              </h4>
              <div
                style={{
                  fontSize: 13,
                  color: "var(--text-primary)",
                  lineHeight: 1.6,
                  whiteSpace: "pre-wrap",
                }}
              >
                {detail.description || "No description"}
              </div>
            </div>

            {/* Plan Steps */}
            {planSteps.length > 0 && (
              <div>
                <h4
                  style={{
                    fontSize: 12,
                    color: "var(--text-secondary)",
                    marginBottom: 8,
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                  }}
                >
                  Plan Steps
                </h4>
                <PlanStepsTimeline
                  steps={planSteps}
                  zoubaoCount={zoubao?.length ?? detail.zoubao?.length ?? 0}
                  latestZoubaoText={detail.latest_zoubao || undefined}
                />
              </div>
            )}

            {/* Output / Summary / Error */}
            {detail.output && (
              <div className="mt-6">
                <h4
                  style={{
                    fontSize: 12,
                    color: "var(--text-secondary)",
                    marginBottom: 8,
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                  }}
                >
                  Output
                </h4>
                <div
                  style={{
                    fontSize: 13,
                    color: "var(--text-primary)",
                    lineHeight: 1.5,
                    whiteSpace: "pre-wrap",
                    padding: 12,
                    backgroundColor: "var(--surface-2)",
                    borderRadius: 4,
                  }}
                >
                  {detail.output}
                </div>
              </div>
            )}

            {detail.summary && (
              <div className="mt-6">
                <h4
                  style={{
                    fontSize: 12,
                    color: "var(--text-secondary)",
                    marginBottom: 8,
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                  }}
                >
                  Summary
                </h4>
                <div
                  style={{
                    fontSize: 13,
                    color: "var(--text-primary)",
                    lineHeight: 1.5,
                    whiteSpace: "pre-wrap",
                  }}
                >
                  {detail.summary}
                </div>
              </div>
            )}

            {detail.error && (
              <div className="mt-6">
                <h4
                  style={{
                    fontSize: 12,
                    color: "var(--state-failed)",
                    marginBottom: 8,
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                  }}
                >
                  Error
                </h4>
                <div
                  style={{
                    fontSize: 13,
                    color: "var(--state-failed)",
                    lineHeight: 1.5,
                    whiteSpace: "pre-wrap",
                    padding: 12,
                    backgroundColor: "rgba(231,76,60,0.08)",
                    borderRadius: 4,
                  }}
                >
                  {detail.error}
                </div>
              </div>
            )}
          </div>
        </TabsContent>

        {/* Transfer History */}
        <TabsContent value="transfer">
          <div
            className="mt-4"
            style={{
              backgroundColor: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: 20,
            }}
          >
            {liuzhuan === null ? (
              <div style={{ color: "var(--text-secondary)", fontSize: 13 }}>
                Loading...
              </div>
            ) : (
              <LiuzhuanTimeline entries={liuzhuan} />
            )}
          </div>
        </TabsContent>

        {/* Review Votes */}
        <TabsContent value="votes">
          <div
            className="mt-4"
            style={{
              backgroundColor: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: 20,
            }}
          >
            {toupiao === null ? (
              <div style={{ color: "var(--text-secondary)", fontSize: 13 }}>
                Loading...
              </div>
            ) : (
              <ToupiaoPanel entries={toupiao} />
            )}
          </div>
        </TabsContent>

        {/* Progress Feed */}
        <TabsContent value="progress">
          <div
            className="mt-4"
            style={{
              backgroundColor: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: 20,
            }}
          >
            <ZoubaoFeed
              zouzheId={id}
              initialEntries={zoubao ?? detail.zoubao ?? []}
            />
          </div>
        </TabsContent>

        {/* Dispatch Log */}
        <TabsContent value="log">
          <div
            className="mt-4"
            style={{
              backgroundColor: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: 20,
            }}
          >
            <DispatchLogView
              zouzheId={id}
              assignedAgent={detail.assigned_agent}
            />
          </div>
        </TabsContent>
      </Tabs>

      {/* Modals */}
      <ReviseModal
        open={showRevise}
        onClose={() => setShowRevise(false)}
        zouzheId={id}
      />
      <DecideModal
        open={showDecide}
        onClose={() => setShowDecide(false)}
        zouzheId={id}
      />
    </div>
  );
}
