"""MCP-style tool layer: typed results, pure functions, no agent involvement."""
import tools
from tools.types import AssetHealth, CpkTrend, LineStatus


async def test_get_asset_health_typed():
    h = await tools.call_tool("get_asset_health", asset_id="DRAW-01")
    assert isinstance(h, AssetHealth)
    assert h.health_score == 89
    assert h.lockout is False


async def test_get_line_status_ops():
    ls = await tools.call_tool("get_line_status", asset_id="RESPOOL-04")
    assert isinstance(ls, LineStatus)
    assert ls.ops == ["split", "respool"]
    assert ls.cap_h == 30


async def test_get_cpk_trend_subfloor_part():
    c = await tools.call_tool("get_cpk_trend", part_key="PMF-SPEC")
    assert isinstance(c, CpkTrend)
    assert c.cpk == 0.92


async def test_queue_state_overlap_logic():
    board = [{"order_id": "X", "asset_id": "DRAW-01", "start": 5, "dur": 10, "status": "committed"}]
    hit = await tools.call_tool("get_queue_state", asset_id="DRAW-01",
                                start_hr=0, dur_h=10, board=board)
    miss = await tools.call_tool("get_queue_state", asset_id="DRAW-01",
                                 start_hr=15, dur_h=10, board=board)
    assert hit.overlap is True
    assert miss.overlap is False


async def test_material_and_lead():
    m = await tools.call_tool("get_material_availability", part_key="ULL-G654E")
    lead = await tools.call_tool("get_supplier_lead_time", part_key="ULL-G654E")
    assert m.on_hand_km == 140
    assert lead.lead_days == 4


async def test_state_snapshots_match_demo_shapes():
    assets = await tools.call_tool("list_assets")
    parts = await tools.call_tool("list_parts")
    orders = await tools.call_tool("list_work_orders")
    assert {a["id"] for a in assets} == {"DRAW-01", "DRAW-02", "SPOOL-05", "TEST-03", "RESPOOL-04"}
    assert set(parts["SMF-G652D"]) == {"family", "cpk", "spc", "ncr", "scrap", "matAvail", "lead", "regHold"}
    assert len(orders) == 32
    assert set(orders[0]) == {"id", "part", "op", "qty", "due", "cust", "tier"}
