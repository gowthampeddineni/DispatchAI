# Assumptions (required disclosure before building)

The system prompt instructs: *"If either file is missing or ambiguous, list the
specific assumptions you're forced to make before proceeding."* These are them.

1. **The demo has no WebSocket code.** `dispatchai-demo.html` is a fully
   self-contained, deterministic client-side simulation ("No network, no LLM"
   per its own header comment). There is no existing wire contract to match, so
   the contract in [websocket-contract.md](websocket-contract.md) was **derived from the demo's
   internal data shapes** (agent position objects, the `result` object consumed
   by `finishNegotiation()`, the proposal header, the familiarity meter).
   `frontend/dispatchai-demo-live.html` is a copy of the demo with a thin
   bridge script that hydrates state from the server and renders the streamed
   events through the demo's *unmodified* rendering functions.

2. **The pre-existing `data_csv_files.db` is a different domain.** The CSVs in
   `data CSV files/` describe a CNC machining plant (assets `WC-01`, `MC-01A`,
   customers AutoCorp/FluidSys). The demo frontend hard-codes an
   **optical-fiber plant** (assets `DRAW-01`, `DRAW-02`, `SPOOL-05`, `TEST-03`,
   `RESPOOL-04`; fiber parts `SMF-G652D` … `DSF-SPEC`). Per the system prompt,
   the demo guide defines the domain, so the backend is seeded with the fiber
   plant data extracted from the demo (`python main.py seed` →
   `data/dispatchai.db`, schema modeled on the CSV tables so the user's real
   data can be swapped in later). `data_csv_files.db` is left untouched.

3. **Board state lives on the client; the server is stateless per request.**
   The demo manages the Gantt board, trays and CHECK/ACT learning entirely
   client-side. Rather than mirroring that state server-side (sync drift in a
   POC), `schedule_order` carries a snapshot of the client board (for overlap
   checks / "next clear window" fixes) and the client's learned familiarity
   spread. Re-votes on drag-reschedule reuse the demo's local policy mirror —
   the rules are identical to the server's deterministic core.

4. **LLM is optional at runtime; rules are the guardrail.** OpenAI is the
   locked provider and is used when `OPENAI_API_KEY` is set (`gpt-4o-mini` for
   agent position formation, `gpt-4o` for orchestrator synthesis). Hard-veto
   conditions (lockout, line down, reg hold, sub-floor Cpk, missing material)
   are **always enforced deterministically** — an LLM cannot un-veto a safety
   stop. Without a key the system degrades to the deterministic policy engine
   (the same thresholds the demo uses), so the POC runs end-to-end offline.
   This is graceful degradation, not a provider substitution.

5. **"Positions" in the system prompt** maps to the demo's agent positions
   (`ACCEPT/CONCEDE/OBJECT` + `VETO`), streamed as `agent_position` events.

6. **Auto-Schedule All** stays a client-side loop (as in the demo) that issues
   one `schedule_order` per order; the multi-agent concurrency lives inside
   each negotiation (4 subagents fan out in parallel per LangGraph super-step).
