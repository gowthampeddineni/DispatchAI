# DispatchAI WebSocket Contract (v1)

Transport: WebSocket at `ws://<host>:<port>/ws`. All frames are JSON text.

This contract is **derived from `dispatchai-demo.html`**: the original demo is a
self-contained client-side simulation (no network code), so the message shapes
below mirror the demo's internal data structures exactly — agent positions
(`ACCEPT | CONCEDE | OBJECT` + hard `VETO`), the orchestrator verdict
(`COMMIT | ESCALATE | REJECT`), the proposal header, and the familiarity meter.
`frontend/dispatchai-demo-live.html` is the same demo with a thin bridge that
replaces the local simulation with this stream.

## Client → Server

```jsonc
// request the initial snapshot (assets, parts, order queue) — sourced from SQLite via MCP-style tools
{ "type": "get_state" }

// negotiate one order. asset_id/start_hr are optional — the server plans the
// slot if omitted. board is the client's current Gantt state (used for
// overlap checks / next-clear-window fixes). fam_spread/fam_runs carry the
// client's learned familiarity so CHECK/ACT learning still tightens verdicts.
{
  "type": "schedule_order",
  "order": { "id": "WO-4471", "part": "SMF-G652D", "op": "draw",
             "qty": 160, "due": 5, "cust": "Telco North", "tier": "T1" },
  "asset_id": "DRAW-01",        // optional
  "start_hr": 12.0,             // optional, hours from plant t0
  "fam_spread": 1.0,            // optional, default 1.0
  "board": [                    // optional, default []
    { "order_id": "WO-4469", "asset_id": "DRAW-01", "start": 0, "dur": 23.5, "status": "committed" }
  ]
}

// liveness
{ "type": "ping" }
```

## Server → Client — envelope

Every server frame uses one envelope:

```jsonc
{
  "v": 1,                    // contract version
  "type": "run_started",     // event type, see below
  "run_id": "8f0c…",         // one dispatch negotiation, end-to-end (also the LangSmith tag)
  "seq": 2,                  // monotonic per run
  "ts": "2026-06-11T09:00:00.000Z",
  "agent_id": "maint",       // maint | prod | qual | supp | orchestrator | null
  "terminal": false,         // true on the last frame of a run
  "payload": { }
}
```

## Event types

| type | agent_id | payload |
|---|---|---|
| `state` | – | `{ assets: [...], parts: {...}, orders: [...] }` in the demo's own shapes |
| `run_started` | – | `{ order, part_key, part_family, asset_id, asset_name, start_hr, start_label, dur_h, qty_km, customer }` |
| `agent_started` | agent | `{ agent: { id, name, source } }` |
| `agent_position` | agent | `{ pos: "ACCEPT"\|"CONCEDE"\|"OBJECT", veto: bool, sev: 0-3, why: str, tool: str }` |
| `agent_degraded` | agent | `{ error: str }` — agent failed after retry; a CONCEDE placeholder position follows |
| `orchestrator_note` | orchestrator | `{ note, confidence: 0-1, familiarity: { z, zone: "familiar"\|"marginal"\|"outlier", pct } }` |
| `verdict` | orchestrator | see below — **terminal: true** |
| `error` | – | `{ message }` — terminal if the run cannot continue |
| `pong` | – | `{}` |

### `verdict` payload

Contains everything the demo's `finishNegotiation()`/`commit()` need to keep
working unchanged (positions map `A`, vote counts, familiarity, suggested fix):

```jsonc
{
  "outcome": "COMMIT",            // COMMIT | ESCALATE | REJECT
  "acc": 3, "con": 1, "obj": 0,   // vote counts
  "note": "3 accept · 1 concede · 0 object. Consensus reached.",
  "confidence": 0.9,
  "familiarity": { "z": 0.62, "zone": "familiar", "pct": 24.8 },
  "suggested_fix": null,          // string for ESCALATE/REJECT
  "positions": {                  // == demo's result.A
    "maint": { "pos": "ACCEPT", "veto": false, "sev": 0, "why": "…", "tool": "…" },
    "prod":  { },
    "qual":  { },
    "supp":  { }
  },
  "schedule": { "order": { }, "part_key": "SMF-G652D",
                "asset_id": "DRAW-01", "start_hr": 12.0, "dur_h": 23.5 }
}
```

### Event order per run

`run_started` → 4 × (`agent_started`, `agent_position`) interleaved in completion
order (agents run **concurrently**; positions stream as each agent lands) →
`orchestrator_note` → `verdict` (terminal).

## Verdict rules (mirrors the demo exactly)

1. any hard veto → `REJECT`
2. objections ≥ 3 → `REJECT`
3. objections ≥ 1 → `ESCALATE`
4. zero accepts → `ESCALATE`
5. else `COMMIT`, confidence `0.6 + 0.1·accepts`
6. familiarity safety net: a COMMIT in the `outlier` zone becomes `ESCALATE`;
   `marginal` lowers confidence by 0.1.
