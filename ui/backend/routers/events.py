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


async def _event_generator():
    """Generate SSE events: heartbeat every 5s, zouzhe_update on DB changes."""
    last_snapshot: dict[str, str] = {}

    # Initialize snapshot
    try:
        db = await get_db()
        last_snapshot = await _get_zouzhe_snapshot(db)
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
            finally:
                await db.close()

            # Find changed zouzhe
            for zid, updated_at in current_snapshot.items():
                if last_snapshot.get(zid) != updated_at:
                    # Fetch the updated zouzhe
                    db2 = await get_db()
                    try:
                        cursor = await db2.execute(
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
                    finally:
                        await db2.close()

            # Check for removed zouzhe
            for zid in set(last_snapshot) - set(current_snapshot):
                yield {
                    "event": "zouzhe_removed",
                    "data": json.dumps({"id": zid}),
                }

            last_snapshot = current_snapshot

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
