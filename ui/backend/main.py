"""Chaoting Web UI — FastAPI backend."""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import agents, events, zouzhe

app = FastAPI(title="Chaoting Web UI API", version="0.1.0")

# CORS — allow the Next.js dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(zouzhe.router)
app.include_router(agents.router)
app.include_router(events.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
