"""Orchestrator vote rules + familiarity safety net (pure functions)."""
from domain import AgentPosition, Familiarity
from orchestrator.verdict import decide, familiarity


def pos(p="ACCEPT", veto=False, sev=0):
    return AgentPosition(pos=p, veto=veto, sev=sev, why="w", tool="t")


def four(maint="ACCEPT", prod="ACCEPT", qual="ACCEPT", supp="ACCEPT", veto_on=None):
    d = {"maint": pos(maint), "prod": pos(prod), "qual": pos(qual), "supp": pos(supp)}
    if veto_on:
        d[veto_on] = pos("OBJECT", veto=True, sev=3)
    return d


FAMILIAR = Familiarity(z=0.5, zone="familiar", pct=20)


def test_hard_veto_rejects():
    outcome, conf, note = decide(four(veto_on="qual"), FAMILIAR)
    assert outcome == "REJECT" and conf == 0 and "Hard veto" in note


def test_majority_objection_rejects():
    outcome, *_ = decide(four("OBJECT", "OBJECT", "OBJECT", "ACCEPT"), FAMILIAR)
    assert outcome == "REJECT"


def test_single_objection_escalates():
    outcome, conf, _ = decide(four(qual="OBJECT"), FAMILIAR)
    assert outcome == "ESCALATE" and conf == 0.4


def test_all_concede_escalates():
    outcome, *_ = decide(four("CONCEDE", "CONCEDE", "CONCEDE", "CONCEDE"), FAMILIAR)
    assert outcome == "ESCALATE"


def test_consensus_commits_with_confidence():
    outcome, conf, _ = decide(four(), FAMILIAR)
    assert outcome == "COMMIT" and conf == 0.95  # 0.6 + 0.1*4, capped


def test_outlier_overrides_commit():
    outlier = Familiarity(z=2.5, zone="outlier", pct=100)
    outcome, conf, note = decide(four(), outlier)
    assert outcome == "ESCALATE" and "OUTLIER" in note


def test_familiarity_zones():
    normal = familiarity(dur_h=17, cap_h=48, cpk=1.4, due_days=6, lead_days=1, health=80)
    assert normal.zone == "familiar"
    weird = familiarity(dur_h=48, cap_h=48, cpk=0.9, due_days=2, lead_days=4, health=40)
    assert weird.zone == "outlier"
    tighter = familiarity(dur_h=17, cap_h=48, cpk=1.4, due_days=6, lead_days=1,
                          health=80, spread=0.3)
    assert tighter.z > normal.z  # learning tightens "normal"
