# DispatchAI — Multi-Agent Backend (POC)

End-to-end multi-agent backend powering the **DispatchAI demo**: a **LangGraph
orchestrator** fans out four specialized **LangChain subagents** (Maintenance,
Production, Quality, Supply Chain), each consulting its own source system
through **MCP-style tool interfaces** backed by SQLite, and streams the live
negotiation to the demo UI over **WebSocket** — with end-to-end tracing in
**LangSmith**.

```
                 ┌──────────────────────────┐
   WebSocket     │  FastAPI server (async)  │   server/
 demo ◀────────▶ │  /ws + /  (live demo)    │
                 └────────────┬─────────────┘
                              │
                 ┌────────────▼─────────────┐
                 │  Orchestrator Agent      │   orchestrator/
                 │  (LangGraph state graph) │   plan → fan-out → verdict
                 └────────────┬─────────────┘
        ┌────────────┬────────┴──────┬────────────┐
        ▼            ▼               ▼            ▼
   Maintenance   Production      Quality     Supply Chain     agents/
     (CMMS)      (MES/ERP)       (QMMS)         (ERP)
        │            │               │            │
        ▼            ▼               ▼            ▼
   ┌──────────────────────────────────────────────────┐
   │  MCP-style tool layer  (18 typed tools)          │   tools/
   │  Phase 1: SQLite-backed · swappable to real MCP  │
   └──────────────────────────────────────────────────┘
```

Every dispatch request is a negotiation: each agent independently answers
**ACCEPT / CONCEDE / OBJECT** (or raises a hard **VETO**), and the Orchestrator
turns the vote into **COMMIT / ESCALATE / REJECT** with a familiarity safety
net and a concrete 💡 suggested fix.

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate              # Windows
pip install -r requirements.txt

copy .env.example .env              # then fill in your keys (optional, see below)

python main.py serve                # seeds the DB on first run
```

Open **http://127.0.0.1:8000/** — that's the demo (`frontend/dispatchai-demo-live.html`)
served with a live WebSocket bridge. A badge bottom-right shows
**● LIVE multi-agent backend** when connected. Click any order in the queue
(or **▶ Auto-Schedule All**) and watch the four agents stream their positions.

Two ways to see the backend at work directly:

- **🟢 Ask DispatchAI** (bottom-right) — a plant copilot chatting over the same
  WebSocket. Ask *"Why would WO-4480 fail?"*, *"Which line is in the best
  shape?"*, *"Status of MMF-OM4?"* — every CMMS / MES / QMMS / ERP tool call the
  backend makes streams in as a colored chip, and `negotiate_order` dry-runs the
  full four-agent negotiation without touching the board. Works without an
  OpenAI key too (deterministic lookup mode).
- **+ New Order** (queue panel) — enter your own work order (fiber type, op,
  quantity, due date, customer) and hit **🤝 Negotiate now**: it goes through
  the real LangGraph fan-out and lands on the board with a verdict.

Other entry points:

```bash
python main.py demo                 # one full negotiation in the terminal
python main.py demo WO-4480         # ...for a specific queued order
python main.py seed                 # rebuild data/dispatchai.db from scratch
pytest                              # 41 tests: tools, agents, verdict, chat, WS smoke
```

## Environment variables (`.env`)

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | enables the LLM path; **without it the system still runs end-to-end** on the deterministic policy engine |
| `DISPATCHAI_SMALL_MODEL` | light work: agent position formation, extraction (default `gpt-4o-mini`) |
| `DISPATCHAI_LARGE_MODEL` | complex work: orchestrator synthesis, conflict notes (default `gpt-4o`) |
| `DISPATCHAI_LLM_MODE` | `auto` (default) / `live` / `rules` |
| `LANGSMITH_TRACING` + `LANGSMITH_API_KEY` + `LANGSMITH_PROJECT` | auto-traces every orchestrator, agent and tool call; one trace per dispatch request, tagged with the `run_id` from the WebSocket envelope |
| `DISPATCHAI_HOST` / `DISPATCHAI_PORT` | server bind (default `127.0.0.1:8000`) |
| `DISPATCHAI_DB` | SQLite path (default `data/dispatchai.db`) |

LLM routing is by **task complexity, not agent identity** — see
`Settings.model_for()` in [config/settings.py](config/settings.py). Hard vetoes
(lockout, line down, reg hold, sub-floor Cpk, missing material) are always
enforced deterministically; an LLM can refine a position but never un-veto a
safety stop.

## Project layout

| Path | What lives there |
|---|---|
| `config/` | env-driven settings, two-tier model routing |
| `tools/` | MCP-style tool layer (CMMS / MES / QMMS / ERP), SQLite backend — the only code that touches the DB |
| `agents/` | the four LangChain subagents + LLM tiering with rules fallback |
| `orchestrator/` | LangGraph graph, slot planner, verdict rules, familiarity, suggested fixes |
| `server/` | FastAPI app, WebSocket endpoint, versioned message schema |
| `data/` | seed script → `dispatchai.db` (fiber-plant domain from the demo) |
| `frontend/` | `dispatchai-demo-live.html` = original demo + WebSocket bridge |
| `tests/` | tools / agent-policy / verdict / end-to-end WS smoke tests |
| `docs/` | [websocket-contract.md](docs/websocket-contract.md) · [assumptions.md](docs/assumptions.md) · system prompt |

The original `dispatchai-demo.html` is untouched and still works standalone.

## WebSocket contract (v1)

Documented in [docs/websocket-contract.md](docs/websocket-contract.md). Per
negotiation: `run_started` → 4 × `agent_position` (streamed in completion
order — agents run concurrently) → `orchestrator_note` → `verdict`
(terminal). Copilot turns: `chat_started` → n × `chat_tool_call` (live, one per
source-system query) → `chat_response` (terminal). Client sends `get_state` /
`schedule_order` / `chat` / `ping`.

## Build phases (each one was kept runnable)

1. **Skeleton & contract** — FastAPI + WS envelope derived from the demo
2. **Single agent** — Maintenance agent + SQLite-backed CMMS tools
3. **Orchestrator** — LangGraph state machine routing to agents
4. **Multi-agent fan-out** — all four agents concurrent, partials streamed
5. **LLM tiering** — small/large OpenAI routing, configurable per task
6. **Observability & resilience** — LangSmith auto-tracing; per-agent retry → degrade-to-CONCEDE so one failing agent never kills a run
7. **MCP swap (future)** — re-register the same tool names against real MCP servers; agent code does not change

## Definition of done — status

- ✅ demo connects over WebSocket and renders streamed multi-agent updates
- ✅ LangGraph orchestrator fans out to 4 concurrent LangChain subagents
- ✅ all CRM/DB access via MCP-style SQLite-backed tools (no DB calls in agents)
- ✅ small/large OpenAI models routed by task, configurable via env
- ✅ LangSmith traces every agent + tool call under one run id
- ✅ single command start (`python main.py serve`) + this README
