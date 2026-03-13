import type { AgentStatus, ZouzheDetail, ZouzheListItem } from "./types";

const API_BASE = "/api";

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export async function fetchZouzheList(params?: {
  state?: string;
  agent?: string;
  priority?: string;
  limit?: number;
  offset?: number;
}): Promise<ZouzheListItem[]> {
  const searchParams = new URLSearchParams();
  if (params?.state) searchParams.set("state", params.state);
  if (params?.agent) searchParams.set("agent", params.agent);
  if (params?.priority) searchParams.set("priority", params.priority);
  if (params?.limit) searchParams.set("limit", String(params.limit));
  if (params?.offset) searchParams.set("offset", String(params.offset));
  const qs = searchParams.toString();
  return fetchJson<ZouzheListItem[]>(
    `${API_BASE}/zouzhe${qs ? `?${qs}` : ""}`
  );
}

export async function fetchZouzheDetail(id: string): Promise<ZouzheDetail> {
  return fetchJson<ZouzheDetail>(`${API_BASE}/zouzhe/${id}`);
}

export async function fetchAgents(): Promise<AgentStatus[]> {
  return fetchJson<AgentStatus[]>(`${API_BASE}/agents`);
}

export async function fetchStateStats(): Promise<Record<string, number>> {
  const data = await fetchJson<{ stats: Record<string, number> }>(
    `${API_BASE}/stats`
  );
  return data.stats;
}
