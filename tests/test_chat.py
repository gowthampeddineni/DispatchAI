"""Plant copilot chat: rules-mode answers (tool-backed) + WS contract."""
from fastapi.testclient import TestClient

from server.app import app
from server.chat import handle_chat, _tool_schemas
from server.schema import ChatMessage


async def collect(text: str):
    events = []

    async def send(etype, agent_id, payload):
        events.append((etype, payload))

    await handle_chat(ChatMessage(type="chat", text=text), send)
    return events


def test_chat_exposes_registry_plus_negotiate():
    names = {s["function"]["name"] for s in _tool_schemas()}
    assert "negotiate_order" in names
    assert "get_asset_health" in names and "get_cpk_trend" in names
    assert "get_queue_state" not in names          # board-shaped arg, chat-excluded


async def test_chat_order_question_dry_runs_negotiation():
    events = await collect("Why would WO-4472 fail?")
    types = [e for e, _ in events]
    assert types[0] == "chat_started" and types[-1] == "chat_response"
    tool = next(p for e, p in events if e == "chat_tool_call")
    assert tool["tool"] == "negotiate_order" and tool["source"] == "ORCHESTRATOR"
    text = events[-1][1]["text"]
    assert any(k in text for k in ("COMMIT", "ESCALATE", "REJECT"))
    assert "maint" in text and "supp" in text      # all four positions reported


async def test_chat_asset_question_pulls_cmms_and_mes():
    events = await collect("How is Draw Tower 1 doing?")
    sources = [p["source"] for e, p in events if e == "chat_tool_call"]
    assert "CMMS" in sources and "MES" in sources
    assert "health" in events[-1][1]["text"]


async def test_chat_part_question_pulls_qmms():
    events = await collect("What is the status of MMF-OM4?")
    assert any(p["source"] == "QMMS" for e, p in events if e == "chat_tool_call")
    assert "Cpk" in events[-1][1]["text"]


async def test_chat_smalltalk_returns_help():
    events = await collect("hello")
    assert "OPENAI_API_KEY" in events[-1][1]["text"]


def test_chat_over_websocket():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "chat", "text": "Why would WO-4472 fail?"})
        frames = []
        while True:
            f = ws.receive_json()
            frames.append(f)
            if f["terminal"]:
                break
        types = [f["type"] for f in frames]
        assert types[0] == "chat_started" and types[-1] == "chat_response"
        assert all(f["run_id"].startswith("chat-") for f in frames)
        seqs = [f["seq"] for f in frames]
        assert seqs == sorted(seqs)
