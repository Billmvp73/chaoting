"""Zouzhe (task) API endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query

from ..db import get_db
from ..models import (
    LiuzhuanEntry,
    ToupiaoEntry,
    ZoubaoEntry,
    ZouzheDetail,
    ZouzheListItem,
)

router = APIRouter(prefix="/api", tags=["zouzhe"])


@router.get("/zouzhe", response_model=list[ZouzheListItem])
async def list_zouzhe(
    state: str | None = Query(None),
    agent: str | None = Query(None),
    priority: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List zouzhe with optional filters, joined with latest zoubao text."""
    db = await get_db()
    try:
        conditions: list[str] = []
        params: list[str | int] = []

        if state:
            conditions.append("z.state = ?")
            params.append(state)
        if agent:
            conditions.append("z.assigned_agent = ?")
            params.append(agent)
        if priority:
            conditions.append("z.priority = ?")
            params.append(priority)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        query = f"""
            SELECT z.id, z.title, z.state, z.priority, z.assigned_agent,
                   z.created_at, z.updated_at,
                   (SELECT zb.text FROM zoubao zb
                    WHERE zb.zouzhe_id = z.id
                    ORDER BY zb.timestamp DESC LIMIT 1) AS latest_zoubao
            FROM zouzhe z
            {where}
            ORDER BY z.updated_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [
            ZouzheListItem(
                id=r["id"],
                title=r["title"],
                state=r["state"],
                priority=r["priority"],
                assigned_agent=r["assigned_agent"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                latest_zoubao=r["latest_zoubao"],
            )
            for r in rows
        ]
    finally:
        await db.close()


@router.get("/zouzhe/{zouzhe_id}", response_model=ZouzheDetail)
async def get_zouzhe(zouzhe_id: str):
    """Get full zouzhe detail including liuzhuan, toupiao, zoubao."""
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT id, title, description, state, priority, assigned_agent,
                      plan, output, summary, error, retry_count, exec_revise_count,
                      created_at, updated_at
               FROM zouzhe WHERE id = ?""",
            (zouzhe_id,),
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Zouzhe not found")

        # Parse plan JSON
        plan_raw = row["plan"]
        plan = None
        if plan_raw:
            try:
                plan = json.loads(plan_raw)
            except (json.JSONDecodeError, TypeError):
                plan = {"raw": plan_raw}

        # Fetch liuzhuan
        cur_lz = await db.execute(
            "SELECT id, from_role, to_role, action, remark, timestamp FROM liuzhuan WHERE zouzhe_id = ? ORDER BY timestamp ASC",
            (zouzhe_id,),
        )
        liuzhuan = [LiuzhuanEntry(**dict(r)) for r in await cur_lz.fetchall()]

        # Fetch toupiao
        cur_tp = await db.execute(
            "SELECT id, jishi_id, agent_id, vote, reason, timestamp FROM toupiao WHERE zouzhe_id = ? ORDER BY timestamp ASC",
            (zouzhe_id,),
        )
        toupiao = [ToupiaoEntry(**dict(r)) for r in await cur_tp.fetchall()]

        # Fetch zoubao
        cur_zb = await db.execute(
            "SELECT id, agent_id, text, tokens_used, timestamp FROM zoubao WHERE zouzhe_id = ? ORDER BY timestamp DESC",
            (zouzhe_id,),
        )
        zoubao = [ZoubaoEntry(**dict(r)) for r in await cur_zb.fetchall()]

        # Latest zoubao text
        latest_zoubao = zoubao[0].text if zoubao else None

        return ZouzheDetail(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            state=row["state"],
            priority=row["priority"],
            assigned_agent=row["assigned_agent"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            plan=plan,
            output=row["output"],
            summary=row["summary"],
            error=row["error"],
            retry_count=row["retry_count"] or 0,
            exec_revise_count=row["exec_revise_count"] or 0,
            latest_zoubao=latest_zoubao,
            liuzhuan=liuzhuan,
            toupiao=toupiao,
            zoubao=zoubao,
        )
    finally:
        await db.close()


@router.get("/stats")
async def get_state_stats():
    """Return count of zouzhe grouped by state."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT state, COUNT(*) as cnt FROM zouzhe GROUP BY state"
        )
        rows = await cursor.fetchall()
        return {"stats": {r["state"]: r["cnt"] for r in rows}}
    finally:
        await db.close()
