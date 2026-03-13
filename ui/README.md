# Chaoting Web UI — Frontend

Next.js 14 frontend for the chaoting task management system. Provides a real-time monitoring dashboard with an imperial dark gold theme.

## Setup

```bash
cd ui/
npm install
```

## Run

```bash
cd ui/
npm run dev
```

Open http://localhost:3000

## Build

```bash
cd ui/
npm run build
```

## Backend

This frontend proxies API requests to the FastAPI backend. Start the backend first:

```bash
cd ui/
export CHAOTING_DIR=/path/to/.themachine/.chaoting
source backend/venv/bin/activate
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

> ⚠️ Run the backend from the `ui/` directory (not `ui/backend/`) due to Python relative imports.

See [backend/README.md](./backend/README.md) for full backend setup instructions.

## Features

- **Dashboard** (`/dashboard`): real-time view of all tasks by state with live SSE updates
- **Task detail** (`/zouzhe/:id`): full detail including plan, votes, logs, and history
- **Agents panel** (`/agents`): per-department status overview
- **SSE connection indicator**: bottom-right dot shows live connection status
