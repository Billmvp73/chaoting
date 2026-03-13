export type ZouzheState =
  | "created"
  | "planning"
  | "reviewing"
  | "executing"
  | "done"
  | "failed"
  | "escalated"
  | "timeout";

export interface ZouzheListItem {
  id: string;
  title: string;
  state: ZouzheState;
  priority: string;
  assigned_agent: string | null;
  created_at: string;
  updated_at: string;
  latest_zoubao: string | null;
}

export interface ZouzheDetail extends ZouzheListItem {
  description: string | null;
  plan: Record<string, unknown> | null;
  output: string | null;
  summary: string | null;
  error: string | null;
  retry_count: number;
  exec_revise_count: number;
  liuzhuan: LiuzhuanEntry[];
  toupiao: ToupiaoEntry[];
  zoubao: ZoubaoEntry[];
}

export interface LiuzhuanEntry {
  id: number;
  from_role: string | null;
  to_role: string | null;
  action: string;
  remark: string | null;
  timestamp: string;
}

export interface ToupiaoEntry {
  id: number;
  jishi_id: string;
  agent_id: string;
  vote: string;
  reason: string | null;
  timestamp: string;
}

export interface ZoubaoEntry {
  id: number;
  agent_id: string | null;
  text: string;
  tokens_used: number | null;
  timestamp: string;
}

export interface AgentStatus {
  agent_id: string;
  status: "executing" | "recent" | "idle";
  active_zouzhe_id: string | null;
  active_zouzhe_title: string | null;
  last_activity: string | null;
}
