"""SSE (Server-Sent Events) endpoint for real-time updates."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from ..db import get_db

router = APIRouter(prefix="/api", tags=["events"])


async def _get_zouzhe_snapshot(db) -> dict[str, str]:
    """Get a mapping of zouzhe_id -> updated_at for change detection."""
    cursor = await db.execute("SELECT id, updated_at FROM zouzhe")
    rows = await cursor.fetchall()
    return {r["id"]: r["updated_at"] for r in rows}


async def _get_max_zoubao_id(db) -> int:
    """Get the current maximum zoubao id."""
    cursor = await db.execute("SELECT MAX(id) as max_id FROM zoubao")
    row = await cursor.fetchone()
    return row["max_id"] or 0


async def _event_generator():
    """Generate SSE events: heartbeat every 5s, zouzhe_update and zoubao_new on DB changes."""
    last_snapshot: dict[str, str] = {}
    max_zoubao_id: int = 0

    # Initialize snapshot
    try:
        db = await get_db()
        try:
            last_snapshot = await _get_zouzhe_snapshot(db)
            max_zoubao_id = await _get_max_zoubao_id(db)
        finally:
            await db.close()
    except Exception:
        pass

    poll_interval = 2  # seconds
    heartbeat_interval = 5  # seconds
    elapsed = 0.0

    while True:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        # Check for DB changes
        try:
            db = await get_db()
            try:
                current_snapshot = await _get_zouzhe_snapshot(db)

                # Find changed zouzhe
                for zid, updated_at in current_snapshot.items():
                    if last_snapshot.get(zid) != updated_at:
                        # Fetch the updated zouzhe
                        cursor = await db.execute(
                            """SELECT id, title, state, priority, assigned_agent,
                                      created_at, updated_at
                               FROM zouzhe WHERE id = ?""",
                            (zid,),
                        )
                        row = await cursor.fetchone()
                        if row:
                            yield {
                                "event": "zouzhe_update",
                                "data": json.dumps(
                                    {
                                        "id": row["id"],
                                        "title": row["title"],
                                        "state": row["state"],
                                        "priority": row["priority"],
                                        "assigned_agent": row["assigned_agent"],
                                        "created_at": row["created_at"],
                                        "updated_at": row["updated_at"],
                                    }
                                ),
                            }

                # Check for removed zouzhe
                for zid in set(last_snapshot) - set(current_snapshot):
                    yield {
                        "event": "zouzhe_removed",
                        "data": json.dumps({"id": zid}),
                    }

                last_snapshot = current_snapshot

                # Check for new zoubao entries
                current_max = await _get_max_zoubao_id(db)
                if current_max > max_zoubao_id:
                    cursor = await db.execute(
                        "SELECT id, zouzhe_id, agent_id, text, todos_json, "
                        "tokens_used, timestamp "
                        "FROM zoubao WHERE id > ? ORDER BY id ASC",
                        (max_zoubao_id,),
                    )
                    new_rows = await cursor.fetchall()
                    for r in new_rows:
                        todos = None
                        if r["todos_json"]:
                            try:
                                todos = json.loads(r["todos_json"])
                            except (json.JSONDecodeError, TypeError):
                                todos = None
                        yield {
                            "event": "zoubao_new",
                            "data": json.dumps(
                                {
                                    "zouzhe_id": r["zouzhe_id"],
                                    "id": r["id"],
                                    "agent_id": r["agent_id"],
                                    "text": r["text"],
                                    "todos_json": todos,
                                    "tokens_used": r["tokens_used"],
                                    "timestamp": r["timestamp"],
                                }
                            ),
                        }
                    max_zoubao_id = current_max
            finally:
                await db.close()

        except Exception:
            # DB temporarily unavailable, skip this cycle
            pass

        # Heartbeat
        if elapsed >= heartbeat_interval:
            elapsed = 0.0
            yield {
                "event": "heartbeat",
                "data": json.dumps(
                    {"timestamp": datetime.now(timezone.utc).isoformat()}
                ),
            }


@router.get("/stream")
async def stream_events():
    """SSE endpoint for real-time zouzhe updates."""
    return EventSourceResponse(_event_generator())
