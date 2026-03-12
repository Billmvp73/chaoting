"""Agent status API endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from ..db import get_db
from ..models import AgentStatus

router = APIRouter(prefix="/api", tags=["agents"])


@router.get("/agents", response_model=list[AgentStatus])
async def list_agents():
    """Infer agent statuses from DB activity.

    - executing: has a zouzhe in state=executing with assigned_agent = agent_id
    - recent: had a liuzhuan entry in the last 30 minutes
    - idle: otherwise
    """
    db = await get_db()
    try:
        # 1. Agents currently executing
        cur_exec = await db.execute(
            """SELECT DISTINCT assigned_agent, id, title
               FROM zouzhe
               WHERE state = 'executing' AND assigned_agent IS NOT NULL"""
        )
        executing_rows = await cur_exec.fetchall()
        executing_agents: dict[str, dict] = {}
        for r in executing_rows:
            executing_agents[r["assigned_agent"]] = {
                "zouzhe_id": r["id"],
                "zouzhe_title": r["title"],
            }

        # 2. All known agents from recent liuzhuan (last 24h) + zouzhe assignments
        cur_known = await db.execute(
            """SELECT DISTINCT agent_id FROM (
                SELECT DISTINCT from_role AS agent_id FROM liuzhuan
                    WHERE from_role IS NOT NULL
                      AND timestamp >= datetime('now', '-24 hours')
                UNION
                SELECT DISTINCT to_role AS agent_id FROM liuzhuan
                    WHERE to_role IS NOT NULL
                      AND timestamp >= datetime('now', '-24 hours')
                UNION
                SELECT DISTINCT assigned_agent AS agent_id FROM zouzhe
                    WHERE assigned_agent IS NOT NULL
            )"""
        )
        all_agent_ids = {r["agent_id"] for r in await cur_known.fetchall()}

        # 3. Recent activity (last 30 min)
        cur_recent = await db.execute(
            """SELECT DISTINCT from_role AS agent_id, MAX(timestamp) AS last_ts
               FROM liuzhuan
               WHERE from_role IS NOT NULL
                 AND timestamp >= datetime('now', '-30 minutes')
               GROUP BY from_role"""
        )
        recent_agents: dict[str, str] = {}
        for r in await cur_recent.fetchall():
            recent_agents[r["agent_id"]] = r["last_ts"]

        # 4. Last activity for all agents
        cur_last = await db.execute(
            """SELECT from_role AS agent_id, MAX(timestamp) AS last_ts
               FROM liuzhuan
               WHERE from_role IS NOT NULL
               GROUP BY from_role"""
        )
        last_activity: dict[str, str] = {}
        for r in await cur_last.fetchall():
            last_activity[r["agent_id"]] = r["last_ts"]

        # Build response
        results: list[AgentStatus] = []
        for agent_id in sorted(all_agent_ids):
            if agent_id in executing_agents:
                info = executing_agents[agent_id]
                results.append(
                    AgentStatus(
                        agent_id=agent_id,
                        status="executing",
                        active_zouzhe_id=info["zouzhe_id"],
                        active_zouzhe_title=info["zouzhe_title"],
                        last_activity=last_activity.get(agent_id),
                    )
                )
            elif agent_id in recent_agents:
                results.append(
                    AgentStatus(
                        agent_id=agent_id,
                        status="recent",
                        last_activity=recent_agents[agent_id],
                    )
                )
            else:
                results.append(
                    AgentStatus(
                        agent_id=agent_id,
                        status="idle",
                        last_activity=last_activity.get(agent_id),
                    )
                )

        return results
    finally:
        await db.close()
