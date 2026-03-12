"""Pydantic v2 models for chaoting Web UI API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ZouzheListItem(BaseModel):
    id: str
    title: str
    state: str
    priority: str | None = None
    assigned_agent: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    latest_zoubao: str | None = None


class LiuzhuanEntry(BaseModel):
    id: int
    from_role: str | None = None
    to_role: str | None = None
    action: str | None = None
    remark: str | None = None
    timestamp: str | None = None


class ToupiaoEntry(BaseModel):
    id: int
    jishi_id: str
    agent_id: str
    vote: str
    reason: str | None = None
    timestamp: str | None = None


class ZoubaoEntry(BaseModel):
    id: int
    agent_id: str | None = None
    text: str | None = None
    tokens_used: int | None = None
    timestamp: str | None = None


class ZouzheDetail(ZouzheListItem):
    description: str | None = None
    plan: Any | None = None
    output: str | None = None
    summary: str | None = None
    error: str | None = None
    retry_count: int = 0
    exec_revise_count: int = 0
    liuzhuan: list[LiuzhuanEntry] = []
    toupiao: list[ToupiaoEntry] = []
    zoubao: list[ZoubaoEntry] = []


class AgentStatus(BaseModel):
    agent_id: str
    status: str  # "executing" | "recent" | "idle"
    active_zouzhe_id: str | None = None
    active_zouzhe_title: str | None = None
    last_activity: str | None = None


class StateStats(BaseModel):
    stats: dict[str, int]
