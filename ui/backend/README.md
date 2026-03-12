# Chaoting Web UI — Backend

FastAPI backend for the chaoting Web UI. Reads from the chaoting SQLite database and provides REST + SSE endpoints.

## Setup

```bash
cd ui/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CHAOTING_DB_PATH` | Full path to SQLite DB | (see fallbacks) |
| `CHAOTING_DIR` | Chaoting root directory | (fallback: `~/.themachine/.chaoting/chaoting.db`) |

## API Endpoints

- `GET /api/health` — Health check
- `GET /api/zouzhe` — List zouzhe (query: state, agent, priority, limit, offset)
- `GET /api/zouzhe/{id}` — Zouzhe detail with liuzhuan, toupiao, zoubao
- `GET /api/stats` — State statistics
- `GET /api/agents` — Agent status list
- `GET /api/stream` — SSE real-time events
