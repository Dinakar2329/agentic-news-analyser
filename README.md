# Agentic FactCheck

Agentic FactCheck is a real-time AI investigative operating system for viral news verification. It accepts a claim, spawns async search agents, streams evidence discovery over WebSockets, scores sources, and renders the investigation as a live React Flow graph.

This app estimates factual likelihood from available evidence. It is not legal, financial, medical, emergency, or professional advice.

## Stack

- Frontend: React JSX, Vite, Tailwind CSS via `@tailwindcss/vite`, shadcn-compatible JSX components, Framer Motion, React Flow, Zustand, TanStack Query, Axios.
- Backend: FastAPI, Python 3.12, async SQLAlchemy, SQLite by default, PostgreSQL via `DATABASE_URL`, Pydantic, httpx, BeautifulSoup, WebSockets.
- AI providers: OpenAI, Anthropic, Google Gemini, Mistral, Groq, DeepSeek, and Meta/Llama via Groq-hosted models.
- Search: DuckDuckGo-first provider abstraction, with Tavily reserved for later keyed search.

## Local Setup

PowerShell on this machine blocks `npm.ps1`, so use `cmd /c npm ...` commands on Windows.

Backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item ..\.env.example ..\.env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Frontend:

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

Open `http://localhost:5173`.

## BYOK Security

Users authenticate with local email/password auth. Provider keys are sent to `POST /validate-key`, encrypted server-side with `KEY_ENCRYPTION_SECRET`, stored with only a short key hint, and never written to browser localStorage. Frontend localStorage stores only the JWT demo session token.

For production, replace `JWT_SECRET` and `KEY_ENCRYPTION_SECRET` with long random secrets, enforce HTTPS, configure real CORS origins, and move from demo auto-login to an explicit login screen.

## API Reference

- `POST /auth/register`
- `POST /auth/login`
- `GET /auth/me`
- `GET /models`
- `POST /validate-key`
- `POST /investigate`
- `GET /investigations`
- `GET /investigations/{id}`
- `WS /ws/investigation/{id}`

WebSocket event types:

- `investigation_started`
- `agent_spawned`
- `agent_status`
- `source_found`
- `source_ranked`
- `confidence_updated`
- `graph_updated`
- `orchestrator_summary`
- `final_verdict`
- `error`

## Database

SQLite is the default:

```env
DATABASE_URL=sqlite+aiosqlite:///./agentic_factcheck.db
```

PostgreSQL example:

```env
DATABASE_URL=postgresql+asyncpg://factcheck:factcheck@localhost:5432/factcheck
```

Schema tables include users, encrypted API keys, investigations, events, agents, sources, findings, and graph snapshots. The app creates tables automatically at startup for local development; Alembic scaffolding is included for production migrations.

## Docker

```powershell
Copy-Item .env.example .env
docker compose -f docker/docker-compose.yml up --build
```

With PostgreSQL:

```powershell
docker compose -f docker/docker-compose.yml --profile postgres up --build
```

Set `DATABASE_URL=postgresql+asyncpg://factcheck:factcheck@postgres:5432/factcheck` in `.env` for the backend container to use Postgres.

## Testing

Backend:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```

Frontend:

```powershell
cd frontend
cmd /c npm test
```

## Provider Notes

OpenAI uses the official SDK pattern. Anthropic uses Messages API semantics. Google uses `google-genai`. Mistral is exposed only when the optional `mistralai` SDK is installed in the backend runtime. Groq and DeepSeek are OpenAI-compatible providers with provider-specific base URLs. Meta/Llama is represented through Groq-hosted Llama models in v1.

If no provider key is configured, the app still runs the live investigation pipeline and synthesizes deterministic evidence summaries from gathered source scores.
