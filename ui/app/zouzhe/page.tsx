"use client";

import { FilterBar } from "@/components/zouzhe/FilterBar";
import { ZouzheTable } from "@/components/zouzhe/ZouzheTable";
import { fetchAgents, fetchZouzheList } from "@/lib/api";
import { useChaotingStore } from "@/lib/store";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

const PAGE_SIZE = 20;

function ZouzhePageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  // Read filter state from URL
  const urlStates = searchParams.get("states")?.split(",").filter(Boolean) || [];
  const urlAgent = searchParams.get("agent") || null;
  const urlPriority = searchParams.get("priority") || null;
  const urlSearch = searchParams.get("q") || "";
  const urlPage = parseInt(searchParams.get("page") || "1", 10);

  const [selectedStates, setSelectedStates] = useState<string[]>(urlStates);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(urlAgent);
  const [selectedPriority, setSelectedPriority] = useState<string | null>(urlPriority);
  const [searchQuery, setSearchQuery] = useState(urlSearch);
  const [page, setPage] = useState(urlPage);
  const [agents, setAgents] = useState<string[]>([]);
  const [localData, setLocalData] = useState<
    import("@/lib/types").ZouzheListItem[] | null
  >(null);

  const sseList = useChaotingStore((s) => s.zouzheList);

  // Fetch agents for filter dropdown
  useEffect(() => {
    fetchAgents()
      .then((list) => {
        const names = list.map((a) => a.agent_id);
        setAgents(names);
      })
      .catch(() => {});
  }, []);

  // Update URL when filters change
  const updateUrl = useCallback(
    (
      states: string[],
      agent: string | null,
      priority: string | null,
      q: string,
      p: number
    ) => {
      const params = new URLSearchParams();
      if (states.length > 0) params.set("states", states.join(","));
      if (agent) params.set("agent", agent);
      if (priority) params.set("priority", priority);
      if (q) params.set("q", q);
      if (p > 1) params.set("page", String(p));
      const qs = params.toString();
      router.replace(`/zouzhe${qs ? `?${qs}` : ""}`, { scroll: false });
    },
    [router]
  );

  // Fetch filtered data
  const fetchFiltered = useCallback(async () => {
    try {
      const data = await fetchZouzheList({
        state:
          selectedStates.length > 0 ? selectedStates.join(",") : undefined,
        agent: selectedAgent || undefined,
        priority: selectedPriority || undefined,
        search: searchQuery || undefined,
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      });
      setLocalData(data);
    } catch {
      // fall back to SSE data
    }
  }, [selectedStates, selectedAgent, selectedPriority, searchQuery, page]);

  // Initial load and on filter change
  useEffect(() => {
    fetchFiltered();
    updateUrl(
      selectedStates,
      selectedAgent,
      selectedPriority,
      searchQuery,
      page
    );
  }, [
    fetchFiltered,
    updateUrl,
    selectedStates,
    selectedAgent,
    selectedPriority,
    searchQuery,
    page,
  ]);

  // Use local filtered data if available, otherwise SSE list
  const hasFilters =
    selectedStates.length > 0 ||
    selectedAgent !== null ||
    selectedPriority !== null ||
    searchQuery !== "";

  const displayData = useMemo(() => {
    if (hasFilters && localData !== null) return localData;
    // Apply client-side filtering on SSE list
    let filtered = sseList;
    if (selectedStates.length > 0) {
      filtered = filtered.filter((z) => selectedStates.includes(z.state));
    }
    if (selectedAgent) {
      filtered = filtered.filter((z) => z.assigned_agent === selectedAgent);
    }
    if (selectedPriority) {
      filtered = filtered.filter((z) => z.priority === selectedPriority);
    }
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (z) =>
          z.id.toLowerCase().includes(q) || z.title.toLowerCase().includes(q)
      );
    }
    // Paginate
    const start = (page - 1) * PAGE_SIZE;
    return filtered.slice(start, start + PAGE_SIZE);
  }, [
    hasFilters,
    localData,
    sseList,
    selectedStates,
    selectedAgent,
    selectedPriority,
    searchQuery,
    page,
  ]);

  function handleStatesChange(states: string[]) {
    setSelectedStates(states);
    setPage(1);
  }

  function handleAgentChange(agent: string | null) {
    setSelectedAgent(agent);
    setPage(1);
  }

  function handlePriorityChange(p: string | null) {
    setSelectedPriority(p);
    setPage(1);
  }

  function handleSearchChange(q: string) {
    setSearchQuery(q);
    setPage(1);
  }

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h2
          className="text-xl font-bold"
          style={{ color: "var(--text-primary)" }}
        >
          Tasks
        </h2>
        <div id="action-bar-placeholder" />
      </div>

      {/* Filters */}
      <div className="mb-4">
        <FilterBar
          selectedStates={selectedStates}
          onStatesChange={handleStatesChange}
          selectedAgent={selectedAgent}
          onAgentChange={handleAgentChange}
          selectedPriority={selectedPriority}
          onPriorityChange={handlePriorityChange}
          searchQuery={searchQuery}
          onSearchChange={handleSearchChange}
          agents={agents}
        />
      </div>

      {/* Table */}
      <div
        style={{
          backgroundColor: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 8,
          overflow: "hidden",
        }}
      >
        <ZouzheTable
          data={displayData}
          onRowClick={(id) => router.push(`/zouzhe/${id}`)}
        />
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between mt-4">
        <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
          Page {page}
        </span>
        <div className="flex gap-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            style={{
              fontSize: 12,
              padding: "4px 12px",
              borderRadius: 4,
              border: "1px solid var(--border)",
              backgroundColor: "var(--surface)",
              color:
                page <= 1 ? "var(--text-secondary)" : "var(--text-primary)",
              cursor: page <= 1 ? "not-allowed" : "pointer",
              opacity: page <= 1 ? 0.5 : 1,
            }}
          >
            Previous
          </button>
          <button
            onClick={() => setPage((p) => p + 1)}
            disabled={displayData.length < PAGE_SIZE}
            style={{
              fontSize: 12,
              padding: "4px 12px",
              borderRadius: 4,
              border: "1px solid var(--border)",
              backgroundColor: "var(--surface)",
              color:
                displayData.length < PAGE_SIZE
                  ? "var(--text-secondary)"
                  : "var(--text-primary)",
              cursor:
                displayData.length < PAGE_SIZE ? "not-allowed" : "pointer",
              opacity: displayData.length < PAGE_SIZE ? 0.5 : 1,
            }}
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ZouzhePage() {
  return (
    <Suspense
      fallback={
        <div className="p-6" style={{ color: "var(--text-secondary)" }}>
          Loading...
        </div>
      }
    >
      <ZouzhePageInner />
    </Suspense>
  );
}
