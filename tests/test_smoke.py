"""End-to-end smoke: one full dispatch request through the LangGraph
orchestrator, and the same through the FastAPI WebSocket contract."""
from fastapi.testclient import TestClient

from domain import Order, Proposal
from orchestrator import plan_slot, run_negotiation
from server.app import app


async def test_full_negotiation_streams_and_commits():
    events: list[tuple[str, str | None]] = []

    async def emit(etype, agent_id, payload):
        events.append((etype, agent_id))

    order = Order(id="WO-SMOKE", part="SMF-G652D", op="draw", qty=160, due=6,
                  cust="Telco North", tier="T1")
    asset_id, start_hr, dur_h = await plan_slot(order, [])
    verdict = await run_negotiation(
        Proposal(order=order, part_key=order.part, asset_id=asset_id,
                 start_hr=start_hr, dur_h=dur_h),
        emit, "smoke-run",
    )

    assert verdict.outcome == "COMMIT"
    assert len(verdict.positions) == 4
    types = [e for e, _ in events]
    assert types.count("agent_started") == 4
    assert types.count("agent_position") == 4
    assert types[-2:] == ["orchestrator_note", "verdict"]
    # concurrency: all four agents started before the first position landed
    assert types.index("agent_position") >= 4


async def test_hard_veto_rejects_with_fix():
    order = Order(id="WO-VETO", part="DSF-SPEC", op="draw", qty=160, due=5,
                  cust="Hyperscale DC", tier="T2")
    asset_id, start_hr, dur_h = await plan_slot(order, [])
    verdict = await run_negotiation(
        Proposal(order=order, part_key=order.part, asset_id=asset_id,
                 start_hr=start_hr, dur_h=dur_h))
    assert verdict.outcome == "REJECT"
    assert verdict.suggested_fix and "sign-off" in verdict.suggested_fix


def test_websocket_contract_end_to_end():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        # state snapshot
        ws.send_json({"type": "get_state"})
        state = ws.receive_json()
        assert state["v"] == 1 and state["type"] == "state"
        assert len(state["payload"]["orders"]) == 32
        order = state["payload"]["orders"][0]

        # one negotiation, slot planned by the server
        ws.send_json({"type": "schedule_order", "order": order, "board": []})
        frames = []
        while True:
            f = ws.receive_json()
            frames.append(f)
            if f["terminal"]:
                break

        types = [f["type"] for f in frames]
        assert types[0] == "run_started"
        assert types.count("agent_position") == 4
        assert types[-1] == "verdict"

        run_ids = {f["run_id"] for f in frames}
        assert len(run_ids) == 1                       # one trace id end-to-end
        seqs = [f["seq"] for f in frames]
        assert seqs == sorted(seqs)                    # monotonic envelope seq

        verdict = frames[-1]["payload"]
        assert verdict["outcome"] in {"COMMIT", "ESCALATE", "REJECT"}
        assert set(verdict["positions"]) == {"maint", "prod", "qual", "supp"}
        assert verdict["schedule"]["asset_id"]


def test_healthz():
    client = TestClient(app)
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json()["ok"] is True
