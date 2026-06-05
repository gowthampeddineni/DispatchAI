# DispatchAI — Demo Guide

**Autonomous production scheduling for an optical-fiber plant, driven by a multi-agent negotiation.**

---

## 2. The big idea (read this first)

A factory runs a **Plan → Do → Check → Act (PDCA)** loop. DispatchAI automates it with **four specialist AI agents** that each consult their *own* source system, form a position **independently** (so they don't anchor on each other), and then an **Orchestrator** runs the vote and decides.

| Agent | Source system | Worries about |
|---|---|---|
| 🟠 **Maintenance** | CMMS | asset health, vibration, PM schedule, lockouts |
| 🔵 **Production** | MES / ERP | line status, capacity, OEE, right equipment |
| 🟢 **Quality** | QMMS | Cpk (process capability), SPC alerts, reg holds |
| 🟣 **Supply Chain** | ERP | material on hand, lead time vs. due date |

Every agent answers **ACCEPT / CONCEDE / OBJECT** (and can raise a hard **VETO**). The Orchestrator turns those votes into one of three verdicts:

- ✅ **COMMIT** — consensus; schedule it.
- ⚠️ **ESCALATE** — not clear-cut; a human should decide.
- ⛔ **REJECT** — a hard blocker (e.g. material out, Cpk below floor); can't run as-is.

---

## 3. The screen at a glance

```
┌───────────────────────────────────────────────────────────────────────────┐
│  HEADER:  DispatchAI logo   │  Plan▸Do▸Check▸Act   │   Trust Ramp L1–L5     │
├───────────────┬───────────────────────────────────────┬─────────────────────┤
│  LEFT          │  CENTER                                │  RIGHT               │
│  Order Queue   │  Production Schedule (Gantt, 5 days)   │  Agent Negotiation   │
│  Escalations   │  ── blocks for committed runs ──       │  (the live debate    │
│  Blocked       │  CHECK/ACT strip (familiarity + %)     │   + verdict + fixes) │
│  Consensus Log │                                        │                      │
└───────────────┴───────────────────────────────────────┴─────────────────────┘
```

- **Left column** — the **Order Queue** fills it by default. **Escalations**, **Blocked Orders**, and **Consensus Log** sit collapsed at the bottom and pop open automatically once they have content. Drag the dividers to resize.
- **Center** — the live **Gantt board**: 5-day, 24/7 horizon with day separators. Five production assets (2 draw towers, spooling, proof/optical test, split & respool).
- **Right** — the **Agent Negotiation** feed: watch the four agents debate, see the Orchestrator's verdict, and (for non-commits) a **💡 Suggested fix**.

---

## 4. Run your first order (the 2-minute happy path)

1. **Click any order** in the Order Queue (left).
2. Watch the **Agent Negotiation** panel (right): each agent reports its position with the data and "tool call" behind it.
3. The **Orchestrator** posts a verdict card:
   - **COMMIT** → click **Approve (1-click)**. A block lands on the Gantt.
   - **ESCALATE** → read the 💡 suggested fix, then **Approve anyway** or **Send to tray**.
   - **REJECT** → **File as blocked** (it parks in Blocked Orders with a suggested fix).
4. Repeat with a few more orders to fill the board.

> 💡 **Tip:** the queue is built to give a realistic spread — most orders COMMIT, some ESCALATE (marginal quality), some get REJECTED (no material / reg hold / sub-floor Cpk).

---

## 5. Schedule the whole queue at once

Click **▶ Auto-Schedule All**. DispatchAI walks the entire queue, plays each negotiation quickly, and routes every order to the board, the Escalations tray, or the Blocked tray. At the end you get a summary toast like:

> *Auto-schedule done · 14 scheduled · 9 escalated · 8 blocked*

This is the best way to show the system handling volume and producing a mixed, realistic outcome.

---

## 6. Manage a block on the board

**Click any block** (or its **`⋯`** at the bottom-right) to open the management menu:

| Action | What it does |
|---|---|
| **✓ Done — run CHECK / ACT** | Marks the run finished and scores it (see §7) |
| **✓ Approve → committed** | Promotes an escalated/approved block to committed |
| **⚠ Hold → escalations** | Pulls it off the board into the Escalations tray |
| **✕ Block → blocked tray** | Moves it to Blocked Orders |
| **↩ Return to queue** | Sends the order back to the Order Queue |
| **🗑 Remove from schedule** | Deletes the block |

**Drag a block** to reschedule it — sideways to change the time, or onto another row to move it to a different line. The agents **re-vote instantly** on the new slot, and the block recolors if the move creates a conflict. Approvals never double-book: if a slot is taken, the run automatically slides to the next clear window.

---

## 7. CHECK / ACT — how the system "learns"

This is the second half of the loop, and the part most people miss.

PLAN/DO scheduled the job. **CHECK/ACT grades whether the agents were right.**

1. Open any committed block → **✓ Done — run CHECK / ACT**.
2. **CHECK:** the same four agents score their own prediction against simulated actuals — each gets a **✓ HIT** or **✕ MISS**. (Misses are more likely on low-health assets, marginal Cpk, or escalated runs.) 3+ hits = **ADHERENT**.
3. **ACT:** the scorecard is written to the Consensus Log, the **Adherence %** updates, and the **familiarity distribution tightens** — the system's idea of "normal" gets sharper, so future outliers are caught more aggressively.

> **This is the only thing that moves the "X runs" and "Adherence %" counters** at the bottom of the Gantt. Scheduling a job ≠ knowing how it turned out. The starting **42 runs / ~93%** is a pre-trained baseline; complete a few runs and watch it climb.

**Proposal Familiarity meter** (bottom-left of center): the needle shows how "normal" the *current* proposal is vs. everything the system has successfully run — **familiar → marginal → outlier**. An outlier can turn an agreed COMMIT into an ESCALATE: *"the agents agree, but we've never seen anything like this — get a human."*

---

## 8. Trust Ramp (L1–L5)

Top-right of the header. This is the **autonomy dial** — how much DispatchAI is allowed to do on its own:

| Level | Mode | Behavior |
|---|---|---|
| **L1** | Shadow | Observes only; logs proposals, commits nothing |
| **L2** | Recommend | Advises; you accept each recommendation |
| **L3** | Approve · 1-click | *(default)* You approve with one click |
| **L4** | Auto (bounded) | Auto-commits safe proposals; escalates outliers |
| **L5** | Auto (full) | Fully autonomous |

The story: you **earn** higher autonomy as adherence proves out. Start in Shadow, graduate as the numbers justify it.

---

## 9. Escalations, Blocked Orders & Suggested Fixes

When an order can't be auto-committed it lands in a tray on the left, each card carrying a **💡 suggested fix** — a concrete next step, not just an error:

- *"Push to the next clear window on Draw Tower 1 at **Tue 14:00**."*
- *"Run the due PM on Proof & Optical Test first, or route to **Draw Tower 2**."*
- *"Only 140 km on hand — split into a 140 km run + backorder, or wait 4d lead."*
- *"Clear the OTDR sign-off, then re-release."*

From a tray card you can **Approve**, **Block**, **Retry** (back to queue), or **Dismiss**. Click a card to **replay the recorded negotiation** that produced it.

---

## 10. Bonus interactions

- **Line status:** click the **● RUNNING** chip on any asset row to cycle **running → idle → down**. Taking a line down re-checks every scheduled run on it and flags conflicts — a quick way to demo disruption handling.
- **+ Add Order:** drop another random work order into the queue.
- **Start mode:** **From scratch** (empty board) or **Around plan** (board pre-loaded with an existing committed schedule the agents must work around).
- **↺ Reset Demo:** fresh queue and board. *(Your Trust Ramp level and the learned familiarity/adherence memory persist across resets — that's intentional.)*
- **Consensus Log:** every commit, override, escalation, reschedule, and scorecard is recorded here as an auditable trail.

---

*DispatchAI demo · optical-fiber plant · Plan → Do → Check → Act*
