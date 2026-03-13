"use client";

import { Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";

const ALL_STATES = [
  "created",
  "planning",
  "reviewing",
  "executing",
  "done",
  "failed",
  "escalated",
  "timeout",
] as const;

const STATE_COLORS: Record<string, string> = {
  created: "var(--state-created)",
  planning: "var(--state-planning)",
  reviewing: "var(--state-reviewing)",
  executing: "var(--state-executing)",
  done: "var(--state-done)",
  failed: "var(--state-failed)",
  escalated: "var(--state-escalated)",
  timeout: "var(--state-timeout)",
};

interface FilterBarProps {
  selectedStates: string[];
  onStatesChange: (states: string[]) => void;
  selectedAgent: string | null;
  onAgentChange: (agent: string | null) => void;
  selectedPriority: string | null;
  onPriorityChange: (p: string | null) => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  agents: string[];
}

export function FilterBar({
  selectedStates,
  onStatesChange,
  selectedAgent,
  onAgentChange,
  selectedPriority,
  onPriorityChange,
  searchQuery,
  onSearchChange,
  agents,
}: FilterBarProps) {
  const [localSearch, setLocalSearch] = useState(searchQuery);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    setLocalSearch(searchQuery);
  }, [searchQuery]);

  function handleSearchInput(value: string) {
    setLocalSearch(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      onSearchChange(value);
    }, 300);
  }

  function toggleState(state: string) {
    if (selectedStates.includes(state)) {
      onStatesChange(selectedStates.filter((s) => s !== state));
    } else {
      onStatesChange([...selectedStates, state]);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {/* State filter badges */}
      <div className="flex flex-wrap items-center gap-1.5">
        {ALL_STATES.map((state) => {
          const active = selectedStates.includes(state);
          const color = STATE_COLORS[state];
          return (
            <button
              key={state}
              onClick={() => toggleState(state)}
              style={{
                fontSize: 11,
                padding: "3px 10px",
                borderRadius: 4,
                border: `1px solid ${active ? color : "var(--border)"}`,
                backgroundColor: active ? `${color}22` : "transparent",
                color: active ? color : "var(--text-secondary)",
                cursor: "pointer",
                transition: "all 0.15s",
              }}
            >
              {state}
            </button>
          );
        })}
      </div>

      {/* Agent / Priority selects + Search */}
      <div className="flex items-center gap-3">
        <select
          value={selectedAgent || ""}
          onChange={(e) => onAgentChange(e.target.value || null)}
          style={{
            fontSize: 12,
            padding: "5px 8px",
            borderRadius: 4,
            border: "1px solid var(--border)",
            backgroundColor: "var(--surface)",
            color: "var(--text-primary)",
          }}
        >
          <option value="">All Agents</option>
          {agents.map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </select>

        <select
          value={selectedPriority || ""}
          onChange={(e) => onPriorityChange(e.target.value || null)}
          style={{
            fontSize: 12,
            padding: "5px 8px",
            borderRadius: 4,
            border: "1px solid var(--border)",
            backgroundColor: "var(--surface)",
            color: "var(--text-primary)",
          }}
        >
          <option value="">All Priorities</option>
          <option value="normal">normal</option>
          <option value="high">high</option>
          <option value="urgent">urgent</option>
        </select>

        <div
          className="flex items-center gap-2 flex-1"
          style={{
            border: "1px solid var(--border)",
            borderRadius: 4,
            padding: "4px 8px",
            backgroundColor: "var(--surface)",
          }}
        >
          <Search size={14} style={{ color: "var(--text-secondary)" }} />
          <input
            type="text"
            placeholder="Search tasks..."
            value={localSearch}
            onChange={(e) => handleSearchInput(e.target.value)}
            style={{
              flex: 1,
              fontSize: 12,
              backgroundColor: "transparent",
              border: "none",
              outline: "none",
              color: "var(--text-primary)",
            }}
          />
        </div>
      </div>
    </div>
  );
}
