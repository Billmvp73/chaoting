"""Zouzhe (task) API endpoints."""

from __future__ import annotations

import json
import os
import re
import subprocess

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBasicCredentials

from ..auth import require_auth
from ..db import get_db
from ..models import (
    CreateZouzheRequest,
    DecideRequest,
    LiuzhuanEntry,
    ReviseRequest,
    ToupiaoEntry,
    ZoubaoEntry,
    ZouzheDetail,
    ZouzheListItem,
)

router = APIRouter(prefix="/api", tags=["zouzhe"])

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


@router.get("/zouzhe", response_model=list[ZouzheListItem])
async def list_zouzhe(
    state: str | None = Query(None),
    agent: str | None = Query(None),
    priority: str | None = Query(None),
    search: str | None = Query(None),
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
        if search:
            conditions.append("(z.title LIKE ? OR z.id LIKE ?)")
            params.append(f"%{search}%")
            params.append(f"%{search}%")

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


# ---------- Sub-resource endpoints (read-only) ----------


@router.get("/zouzhe/{zouzhe_id}/liuzhuan", response_model=list[LiuzhuanEntry])
async def get_liuzhuan(zouzhe_id: str):
    """State-transition audit log for a zouzhe."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, from_role, to_role, action, remark, timestamp "
            "FROM liuzhuan WHERE zouzhe_id = ? ORDER BY timestamp ASC",
            (zouzhe_id,),
        )
        return [LiuzhuanEntry(**dict(r)) for r in await cursor.fetchall()]
    finally:
        await db.close()


@router.get("/zouzhe/{zouzhe_id}/toupiao", response_model=list[ToupiaoEntry])
async def get_toupiao(zouzhe_id: str):
    """Review votes for a zouzhe."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, jishi_id, agent_id, vote, reason, timestamp "
            "FROM toupiao WHERE zouzhe_id = ? ORDER BY timestamp ASC",
            (zouzhe_id,),
        )
        return [ToupiaoEntry(**dict(r)) for r in await cursor.fetchall()]
    finally:
        await db.close()


@router.get("/zouzhe/{zouzhe_id}/zoubao", response_model=list[ZoubaoEntry])
async def get_zoubao(zouzhe_id: str):
    """Progress reports for a zouzhe (includes todos_json)."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, agent_id, text, todos_json, tokens_used, timestamp "
            "FROM zoubao WHERE zouzhe_id = ? ORDER BY timestamp ASC",
            (zouzhe_id,),
        )
        rows = await cursor.fetchall()
        result = []
        for r in rows:
            todos = None
            if r["todos_json"]:
                try:
                    todos = json.loads(r["todos_json"])
                except (json.JSONDecodeError, TypeError):
                    todos = None
            result.append(
                ZoubaoEntry(
                    id=r["id"],
                    agent_id=r["agent_id"],
                    text=r["text"],
                    todos_json=todos,
                    tokens_used=r["tokens_used"],
                    timestamp=r["timestamp"],
                )
            )
        return result
    finally:
        await db.close()


@router.get("/zouzhe/{zouzhe_id}/log")
async def get_log(zouzhe_id: str, agent_id: str = Query(...)):
    """Read agent log file for a zouzhe."""
    if not _SAFE_ID_RE.match(zouzhe_id) or not _SAFE_ID_RE.match(agent_id):
        raise HTTPException(status_code=400, detail="Invalid zouzhe_id or agent_id")

    chaoting_dir = os.environ.get("CHAOTING_DIR", "")
    if not chaoting_dir:
        return {"content": None, "message": "Log not found"}

    log_path = os.path.join(chaoting_dir, "logs", zouzhe_id, f"{agent_id}.log")
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"content": content, "message": "OK"}
    except FileNotFoundError:
        return {"content": None, "message": "Log not found"}


# ---------- Write endpoints (require auth) ----------


def _get_chaoting_cli_path() -> str:
    chaoting_dir = os.environ.get("CHAOTING_DIR", "")
    return os.path.join(chaoting_dir, "..", "src", "chaoting") if chaoting_dir else ""


def _get_cli_env() -> dict[str, str]:
    env = os.environ.copy()
    env["OPENCLAW_AGENT_ID"] = "silijian"
    return env


@router.post("/zouzhe")
async def create_zouzhe(
    request: CreateZouzheRequest,
    _credentials: HTTPBasicCredentials = Depends(require_auth),
):
    """Create a new zouzhe via chaoting CLI."""
    chaoting_path = _get_chaoting_cli_path()
    if not chaoting_path:
        raise HTTPException(status_code=500, detail="CHAOTING_DIR not configured")

    cmd = [
        chaoting_path,
        "new",
        request.title,
        request.description,
        "--priority",
        request.priority,
        "--review",
        str(request.review_required),
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=_get_cli_env(),
    )
    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"CLI error: {result.stderr.strip()}",
        )
    try:
        data = json.loads(result.stdout)
        return {"id": data["id"]}
    except (json.JSONDecodeError, KeyError):
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected CLI output: {result.stdout.strip()}",
        )


@router.post("/zouzhe/{zouzhe_id}/revise")
async def revise_zouzhe(
    zouzhe_id: str,
    request: ReviseRequest,
    _credentials: HTTPBasicCredentials = Depends(require_auth),
):
    """Request revision of a completed zouzhe via chaoting CLI."""
    # Verify state is done
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT state FROM zouzhe WHERE id = ?", (zouzhe_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Zouzhe not found")
        if row["state"] != "done":
            raise HTTPException(
                status_code=400,
                detail=f"Zouzhe state is '{row['state']}', expected 'done'",
            )
    finally:
        await db.close()

    chaoting_path = _get_chaoting_cli_path()
    if not chaoting_path:
        raise HTTPException(status_code=500, detail="CHAOTING_DIR not configured")

    cmd = [
        chaoting_path,
        "revise",
        zouzhe_id,
        request.reason,
        "--review",
        str(request.review_required),
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=_get_cli_env(),
    )
    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"CLI error: {result.stderr.strip()}",
        )
    return {"ok": True}


@router.post("/zouzhe/{zouzhe_id}/decide")
async def decide_zouzhe(
    zouzhe_id: str,
    request: DecideRequest,
    _credentials: HTTPBasicCredentials = Depends(require_auth),
):
    """Decide on an escalated zouzhe via chaoting CLI."""
    # Verify state is escalated
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT state FROM zouzhe WHERE id = ?", (zouzhe_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Zouzhe not found")
        if row["state"] != "escalated":
            raise HTTPException(
                status_code=400,
                detail=f"Zouzhe state is '{row['state']}', expected 'escalated'",
            )
    finally:
        await db.close()

    chaoting_path = _get_chaoting_cli_path()
    if not chaoting_path:
        raise HTTPException(status_code=500, detail="CHAOTING_DIR not configured")

    cmd = [
        chaoting_path,
        "decide",
        zouzhe_id,
        request.verdict,
        request.reason or "",
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=_get_cli_env(),
    )
    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"CLI error: {result.stderr.strip()}",
        )
    return {"ok": True}


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
