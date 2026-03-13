import type {
  AgentStatus,
  CreateZouzheRequest,
  DecideRequest,
  LiuzhuanEntry,
  ReviseRequest,
  ToupiaoEntry,
  ZoubaoEntry,
  ZouzheDetail,
  ZouzheListItem,
} from "./types";

const API_BASE = "/api";

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

function makeAuthHeader(credentials: {
  username: string;
  password: string;
}): string {
  return "Basic " + btoa(`${credentials.username}:${credentials.password}`);
}

export async function fetchZouzheList(params?: {
  state?: string;
  agent?: string;
  priority?: string;
  search?: string;
  limit?: number;
  offset?: number;
}): Promise<ZouzheListItem[]> {
  const searchParams = new URLSearchParams();
  if (params?.state) searchParams.set("state", params.state);
  if (params?.agent) searchParams.set("agent", params.agent);
  if (params?.priority) searchParams.set("priority", params.priority);
  if (params?.search) searchParams.set("search", params.search);
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

// Sub-resource endpoints
export async function fetchLiuzhuan(id: string): Promise<LiuzhuanEntry[]> {
  return fetchJson<LiuzhuanEntry[]>(`${API_BASE}/zouzhe/${id}/liuzhuan`);
}

export async function fetchToupiao(id: string): Promise<ToupiaoEntry[]> {
  return fetchJson<ToupiaoEntry[]>(`${API_BASE}/zouzhe/${id}/toupiao`);
}

export async function fetchZoubao(id: string): Promise<ZoubaoEntry[]> {
  return fetchJson<ZoubaoEntry[]>(`${API_BASE}/zouzhe/${id}/zoubao`);
}

export async function fetchDispatchLog(
  id: string,
  agentId: string
): Promise<{ content: string | null; message: string }> {
  return fetchJson<{ content: string | null; message: string }>(
    `${API_BASE}/zouzhe/${id}/log?agent_id=${encodeURIComponent(agentId)}`
  );
}

// Write operations (with Basic Auth)
export async function createZouzhe(
  req: CreateZouzheRequest,
  credentials: { username: string; password: string }
): Promise<{ id: string }> {
  const res = await fetch(`${API_BASE}/zouzhe`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: makeAuthHeader(credentials),
    },
    body: JSON.stringify(req),
  });
  if (res.status === 401) throw new Error("Unauthorized");
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function reviseZouzhe(
  id: string,
  req: ReviseRequest,
  credentials: { username: string; password: string }
): Promise<{ ok: boolean }> {
  const res = await fetch(`${API_BASE}/zouzhe/${id}/revise`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: makeAuthHeader(credentials),
    },
    body: JSON.stringify(req),
  });
  if (res.status === 401) throw new Error("Unauthorized");
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function decideZouzhe(
  id: string,
  req: DecideRequest,
  credentials: { username: string; password: string }
): Promise<{ ok: boolean }> {
  const res = await fetch(`${API_BASE}/zouzhe/${id}/decide`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: makeAuthHeader(credentials),
    },
    body: JSON.stringify(req),
  });
  if (res.status === 401) throw new Error("Unauthorized");
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}
