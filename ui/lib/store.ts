import { create } from "zustand";
import type { AgentStatus, ZoubaoEntry, ZouzheListItem } from "./types";

interface ChaotingStore {
  zouzheList: ZouzheListItem[];
  stateStats: Record<string, number>;
  agentStatuses: AgentStatus[];
  sseConnected: boolean;
  lastEventAt: string | null;
  credentials: { username: string; password: string } | null;
  detailZoubaoMap: Record<string, ZoubaoEntry[]>;

  setZouzheList: (list: ZouzheListItem[]) => void;
  setStateStats: (stats: Record<string, number>) => void;
  setAgentStatuses: (agents: AgentStatus[]) => void;
  setSseConnected: (connected: boolean) => void;
  applyZouzheUpdate: (updated: ZouzheListItem) => void;
  setCredentials: (c: { username: string; password: string } | null) => void;
  appendZoubaoEntry: (zouzhe_id: string, entry: ZoubaoEntry) => void;
}

export const useChaotingStore = create<ChaotingStore>((set) => ({
  zouzheList: [],
  stateStats: {},
  agentStatuses: [],
  sseConnected: false,
  lastEventAt: null,
  credentials: null,
  detailZoubaoMap: {},

  setZouzheList: (list) => set({ zouzheList: list }),
  setStateStats: (stats) => set({ stateStats: stats }),
  setAgentStatuses: (agents) => set({ agentStatuses: agents }),
  setSseConnected: (connected) => set({ sseConnected: connected }),
  setCredentials: (c) => set({ credentials: c }),

  applyZouzheUpdate: (updated) =>
    set((state) => {
      const idx = state.zouzheList.findIndex((z) => z.id === updated.id);
      const newList =
        idx >= 0
          ? state.zouzheList.map((z, i) => (i === idx ? updated : z))
          : [updated, ...state.zouzheList];

      // Update state stats
      const newStats: Record<string, number> = {};
      for (const z of newList) {
        newStats[z.state] = (newStats[z.state] || 0) + 1;
      }

      return {
        zouzheList: newList,
        stateStats: newStats,
        lastEventAt: new Date().toISOString(),
      };
    }),

  appendZoubaoEntry: (zouzhe_id, entry) =>
    set((state) => {
      const existing = state.detailZoubaoMap[zouzhe_id] || [];
      // Avoid duplicates by id
      if (existing.some((e) => e.id === entry.id)) return state;
      return {
        detailZoubaoMap: {
          ...state.detailZoubaoMap,
          [zouzhe_id]: [...existing, entry],
        },
      };
    }),
}));
