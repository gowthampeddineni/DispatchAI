"""Deterministic verdict core: vote rules, familiarity safety net and
suggested fixes — a faithful port of the demo's orchestrate()/familiarity()/
suggestFix(). The LLM may rephrase the synthesis note; it never changes the
outcome, the counts or the confidence."""
from __future__ import annotations

from tools import call_tool
from domain import CRIT_CPK, AgentPosition, Familiarity, Proposal, Verdict

from .planner import first_free_slot, fmt_t

AGENT_NAMES = {"maint": "Maintenance", "prod": "Production", "qual": "Quality", "supp": "Supply Chain"}

# learned distribution of "normal" proposals (queue/util/cpk/buffer/health)
NORM = {"util": 0.35, "cpk": 1.4, "buffer": 5.0, "health": 80.0}


def familiarity(
    *, dur_h: float, cap_h: float, cpk: float, due_days: int, lead_days: int,
    health: float, spread: float = 1.0,
) -> Familiarity:
    util = dur_h / cap_h
    buffer = due_days - lead_days
    z = (
        abs(util - NORM["util"]) / (0.20 * spread)
        + abs(cpk - NORM["cpk"]) / (0.22 * spread)
        + abs(buffer - NORM["buffer"]) / (3.0 * spread)
        + abs(health - NORM["health"]) / (22.0 * spread)
    ) / 4
    zone = "familiar" if z < 1 else "marginal" if z < 2 else "outlier"
    return Familiarity(z=z, zone=zone, pct=min(100.0, z * 40))


def decide(positions: dict[str, AgentPosition], fam: Familiarity) -> tuple[str, float, str]:
    """Vote rules -> (outcome, confidence, note)."""
    vetoes = [k for k, r in positions.items() if r.veto]
    acc = sum(1 for r in positions.values() if r.pos == "ACCEPT")
    con = sum(1 for r in positions.values() if r.pos == "CONCEDE")
    obj = sum(1 for r in positions.values() if r.pos == "OBJECT")

    if vetoes:
        outcome, confidence = "REJECT", 0.0
        note = f"Hard veto: {', '.join(AGENT_NAMES[k] for k in vetoes)}. Blocking conditions documented."
    elif obj >= 3:
        outcome, confidence = "REJECT", 0.0
        note = f"Majority objection ({obj}/4). Constraints violated."
    elif obj >= 1:
        outcome, confidence = "ESCALATE", 0.4
        note = f"{obj} objection, not dominant. Planner decision required."
    elif acc == 0:
        outcome, confidence = "ESCALATE", 0.35
        note = "Four concessions, zero accepts. No agent will stand behind it."
    else:
        outcome = "COMMIT"
        confidence = 0.6 + 0.1 * acc
        note = f"{acc} accept · {con} concede · {obj} object. Consensus reached."

    # familiarity safety net — consensus without precedent is not enough
    if outcome == "COMMIT" and fam.zone == "outlier":
        outcome, confidence = "ESCALATE", 0.45
        note = ("Agents agreed, but this proposal is an OUTLIER vs every successful "
                "schedule on record. Consensus without precedent is not enough to auto-commit.")
    elif outcome == "COMMIT" and fam.zone == "marginal":
        note += " Familiarity marginal — flagged for elevated monitoring."
        confidence -= 0.1

    return outcome, max(0.0, min(0.95, confidence)), note


async def suggest_fix(proposal: Proposal, positions: dict[str, AgentPosition]) -> str:
    """Turn the dominant blocking reason into a concrete next step."""
    o = proposal.order
    assets = await call_tool("list_assets")
    asset = next(a for a in assets if a["id"] == proposal.asset_id)
    parts = await call_tool("list_parts")
    p = parts[proposal.part_key]

    def alt_lines() -> list[str]:
        return [
            a["name"] for a in assets
            if a["id"] != proposal.asset_id and o.op in a["ops"]
            and a["run"] != "down" and not a["lockout"]
        ]

    blockers = sorted(
        ((k, r) for k, r in positions.items() if r.veto or r.pos == "OBJECT"),
        key=lambda kr: (kr[1].veto, kr[1].sev), reverse=True,
    )
    if not blockers:  # concessions / familiarity outlier — no hard blocker
        slot = first_free_slot(proposal.board, proposal.asset_id, proposal.dur_h)
        return (f"Park in the next clear window on {asset['name']} at "
                f"<b>{fmt_t(slot)}</b>, or approve as-is under elevated monitoring.")

    key = blockers[0][0]
    if key == "qual":
        if p["regHold"]:
            return (f"Clear the customer qualification / OTDR sign-off on "
                    f"{p['family']}, then re-release the order.")
        if p["cpk"] < CRIT_CPK:
            return (f"Hold — Cpk {p['cpk']} is below the {CRIT_CPK} floor. Open a "
                    f"process-capability review on {p['family']} before any {o.op} run; "
                    "this can't be scheduled as-is.")
        return (f"Run a process review on {p['family']} (Cpk {p['cpk']}), "
                "or approve under elevated OTDR screening.")
    if key == "supp":
        if p["matAvail"] < o.qty:
            return (f"Only {p['matAvail']:g} km on hand for a {o.qty} km run. Split into a "
                    f"<b>{p['matAvail']:g} km</b> run now + backorder the rest, or wait for "
                    f"replenishment ({p['lead']}d lead).")
        return (f"Material lead {p['lead']}d misses the {o.due}d date. Expedite the "
                f"preform or renegotiate the commitment with {o.cust}.")
    if key == "maint":
        alts = alt_lines()
        if asset["lockout"]:
            return (f"{asset['name']} is locked out. Route to <b>{alts[0]}</b>, or clear the safety tag first."
                    if alts else
                    f"{asset['name']} is locked out and no alternate {o.op} line is up — "
                    "clear the lockout before scheduling.")
        return (f"Asset condition {asset['health']}%. Run the due PM on {asset['name']} first, "
                f"or route to <b>{alts[0]}</b>."
                if alts else
                f"Asset condition {asset['health']}%. Schedule the overdue PM on "
                f"{asset['name']} before loading this run.")
    if key == "prod":
        alts = alt_lines()
        if asset["run"] == "down":
            return (f"{asset['name']} is DOWN. Move to <b>{alts[0]}</b>, or restore the line."
                    if alts else
                    f"{asset['name']} is DOWN and no alternate {o.op} line is available — restore it first.")
        if o.op not in asset["ops"]:
            return (f"Wrong equipment. Route this {o.op.upper()} run to <b>{alts[0]}</b>."
                    if alts else f"No line is configured for {o.op.upper()}.")
        need = o.qty / asset["rate"]
        if need > asset["capH"]:
            import math
            return (f"Run needs {need:.1f}h vs {asset['name']}'s {asset['capH']:g}h window. Split into "
                    f"<b>{math.ceil(need / asset['capH'])}× ≤{int(asset['capH'] * asset['rate'])} km</b> campaigns.")
        slot = first_free_slot(proposal.board, proposal.asset_id, proposal.dur_h)
        return f"Slot is double-booked. Push to the next clear window on {asset['name']} at <b>{fmt_t(slot)}</b>."
    return "Review the blocking constraint and re-submit."


async def compute_familiarity(proposal: Proposal) -> Familiarity:
    """Pull the familiarity inputs through the same MCP tool layer."""
    health = await call_tool("get_asset_health", asset_id=proposal.asset_id)
    cap_h = await call_tool("get_run_window", asset_id=proposal.asset_id)
    cpk = await call_tool("get_cpk_trend", part_key=proposal.part_key)
    lead = await call_tool("get_supplier_lead_time", part_key=proposal.part_key)
    return familiarity(
        dur_h=proposal.dur_h, cap_h=cap_h, cpk=cpk.cpk,
        due_days=proposal.order.due, lead_days=lead.lead_days,
        health=health.health_score, spread=proposal.fam_spread,
    )


async def build_verdict(proposal: Proposal, positions: dict[str, AgentPosition]) -> Verdict:
    fam = await compute_familiarity(proposal)
    outcome, confidence, note = decide(positions, fam)
    fix = await suggest_fix(proposal, positions) if outcome != "COMMIT" else None
    return Verdict(
        outcome=outcome,
        acc=sum(1 for r in positions.values() if r.pos == "ACCEPT"),
        con=sum(1 for r in positions.values() if r.pos == "CONCEDE"),
        obj=sum(1 for r in positions.values() if r.pos == "OBJECT"),
        note=note, confidence=confidence, familiarity=fam,
        suggested_fix=fix, positions=positions,
    )
