"""Agent policies tested in isolation with synthetic facts (mocked tools)."""
from agents import MaintenanceAgent, ProductionAgent, QualityAgent, SupplyChainAgent
from domain import Order, Proposal


def proposal(**order_kw) -> Proposal:
    base = dict(id="WO-1", part="SMF-G652D", op="draw", qty=160, due=5,
                cust="Telco North", tier="T1")
    base.update(order_kw)
    o = Order(**base)
    return Proposal(order=o, part_key=o.part, asset_id="DRAW-01",
                    start_hr=0.0, dur_h=23.5)


# ---- Maintenance ----

def maint_facts(**kw):
    asset = dict(asset_id="DRAW-01", asset_name="Draw Tower 1", health_score=89,
                 vibration_trend="stable", pm_due_days=11, open_wo_count=0, lockout=False)
    asset.update(kw)
    return {"asset": asset, "vibration": {}, "pm": {}}


def test_maint_lockout_is_hard_veto():
    a = MaintenanceAgent()
    pos = a.hard_veto(maint_facts(lockout=True), proposal())
    assert pos is not None and pos.veto and pos.pos == "OBJECT" and pos.sev == 3


def test_maint_low_health_objects():
    pos = MaintenanceAgent().policy(maint_facts(health_score=40), proposal())
    assert pos.pos == "OBJECT" and not pos.veto


def test_maint_overdue_pm_concedes():
    pos = MaintenanceAgent().policy(maint_facts(pm_due_days=-3), proposal())
    assert pos.pos == "CONCEDE"


def test_maint_healthy_accepts():
    pos = MaintenanceAgent().policy(maint_facts(), proposal())
    assert pos.pos == "ACCEPT" and pos.sev == 0


# ---- Production ----

def prod_facts(**kw):
    line = dict(asset_id="DRAW-01", asset_name="Draw Tower 1", run_state="running",
                ops=["draw"], rate_kmh=7.0, cap_h=48.0)
    line.update(kw.get("line", {}))
    return {"line": line, "oee": {"oee": kw.get("oee", 0.84)},
            "cap_h": line["cap_h"], "queue": {"overlap": kw.get("overlap", False)}}


def test_prod_down_line_is_hard_veto():
    pos = ProductionAgent().hard_veto(prod_facts(line={"run_state": "down"}), proposal())
    assert pos is not None and pos.veto


def test_prod_wrong_op_objects():
    pos = ProductionAgent().policy(prod_facts(), proposal(op="spool"))
    assert pos.pos == "OBJECT" and "Wrong equipment" in pos.why


def test_prod_overlap_objects():
    pos = ProductionAgent().policy(prod_facts(overlap=True), proposal())
    assert pos.pos == "OBJECT" and "double-booked" in pos.why


def test_prod_oversized_run_objects():
    pos = ProductionAgent().policy(prod_facts(), proposal(qty=400))  # 400/7 > 48h
    assert pos.pos == "OBJECT" and "continuous-run window" in pos.why


def test_prod_normal_accepts():
    pos = ProductionAgent().policy(prod_facts(), proposal(qty=160))
    assert pos.pos == "ACCEPT"


# ---- Quality ----

def qual_facts(cpk=1.46, spc=0, ncr=0, scrap=0.5, reg_hold=False):
    return {"cpk": {"part_key": "X", "part_family": "fam", "cpk": cpk},
            "spc": {"active_alerts": spc}, "scrap": {"scrap_pct": scrap},
            "ncr": {"open_ncrs": ncr, "reg_hold": reg_hold, "part_family": "fam"}}


def test_qual_reg_hold_is_hard_veto():
    pos = QualityAgent().hard_veto(qual_facts(reg_hold=True), proposal())
    assert pos is not None and pos.veto and "qualification hold" in pos.why


def test_qual_subfloor_cpk_is_hard_veto():
    pos = QualityAgent().hard_veto(qual_facts(cpk=0.92), proposal())
    assert pos is not None and pos.veto


def test_qual_marginal_cpk_objects():
    assert QualityAgent().policy(qual_facts(cpk=1.10, spc=1), proposal()).pos == "OBJECT"


def test_qual_midband_cpk_concedes():
    assert QualityAgent().policy(qual_facts(cpk=1.30), proposal()).pos == "CONCEDE"


def test_qual_clean_accepts():
    assert QualityAgent().policy(qual_facts(), proposal()).pos == "ACCEPT"


# ---- Supply Chain ----

def supp_facts(avail=9999, lead=1, tier="T2"):
    return {"material": {"on_hand_km": avail}, "lead_days": lead,
            "tier": tier, "part_family": "fam"}


def test_supp_missing_material_is_hard_veto():
    pos = SupplyChainAgent().hard_veto(supp_facts(avail=140), proposal(qty=300))
    assert pos is not None and pos.veto


def test_supp_lead_past_due_objects():
    pos = SupplyChainAgent().policy(supp_facts(lead=7), proposal(due=5))
    assert pos.pos == "OBJECT"


def test_supp_tight_t1_buffer_concedes():
    pos = SupplyChainAgent().policy(supp_facts(lead=3, tier="T1"), proposal(due=5, tier="T1"))
    assert pos.pos == "CONCEDE"


def test_supp_clear_buffer_accepts():
    pos = SupplyChainAgent().policy(supp_facts(lead=1), proposal(due=6))
    assert pos.pos == "ACCEPT"
