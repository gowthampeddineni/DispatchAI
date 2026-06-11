"""Seed data/dispatchai.db with the optical-fiber plant domain.

All values are extracted from dispatchai-demo.html (the source of truth for the
demo domain): 5 production assets, 6 fiber types, and a deliberately balanced
order queue (~16 COMMIT / ~8 ESCALATE / ~8 REJECT) so a full auto-schedule
produces the realistic spread described in DispatchAI-Demo-Guide.md.

Schema is modeled on the user's CSV tables (assets / asset_health /
oee_history / vibration_readings / quality / materials / work_orders) so real
source-system extracts can replace this seed later without touching the tools.
"""
from __future__ import annotations

import random
import sqlite3
from pathlib import Path

# ---- demo ASSETS (CMMS + MES signals) ----
ASSETS = [
    # id, name, type, ops, health, vib, pm_days, open_wo, lockout, run, oee, rate, cap_h
    ("DRAW-01", "Draw Tower 1", "25m tower · dual-coat", "draw", 89, "stable", 11, 0, 0, "running", 0.84, 7, 48),
    ("DRAW-02", "Draw Tower 2", "30m tower · spec fiber", "draw", 78, "stable", 14, 1, 0, "running", 0.76, 9, 48),
    ("SPOOL-05", "Primary Spooling", "precision winder · tension ctrl", "spool", 83, "stable", 22, 0, 0, "running", 0.88, 16, 28),
    ("TEST-03", "Proof & Optical Test", "tensile screen · OTDR", "test", 74, "stable", 19, 1, 0, "running", 0.81, 18, 26),
    ("RESPOOL-04", "Split & Respool", "rewind · drum cut", "split,respool", 71, "stable", 16, 1, 0, "running", 0.74, 14, 30),
]

# ---- demo PARTS (QMMS + ERP signals on the fiber type) ----
PARTS = [
    # key, family, cpk, spc, ncr, scrap, mat_avail, lead, reg_hold
    ("SMF-G652D", "SMF · G.652.D", 1.46, 0, 0, 0.5, 9999, 1, 0),
    ("BIF-G657A2", "BIF · G.657.A2", 1.30, 0, 0, 0.9, 9999, 2, 0),
    ("MMF-OM4", "MMF · OM4", 1.10, 1, 0, 2.0, 9999, 2, 0),
    ("ULL-G654E", "ULL · G.654.E", 1.18, 0, 0, 1.1, 140, 4, 0),
    ("PMF-SPEC", "PM fiber · spec", 0.92, 2, 1, 5.4, 9999, 3, 0),
    ("DSF-SPEC", "DSF · dispersion-shifted", 1.25, 0, 0, 1.2, 9999, 3, 1),
]

CUSTS = [
    ("Tier-1 Cable OEM", "T1"), ("Hyperscale DC", "T2"), ("Submarine Networks", "T1"),
    ("Telco North", "T1"), ("Internal Stock", "T3"), ("Regional ISP", "T2"),
    ("Defense Optics", "T3"), ("Metro Fiber Co", "T2"), ("Backbone Telecom", "T1"),
]

OP_POOL = ["draw", "draw", "spool", "spool", "test", "split", "respool", "respool"]

SCHEMA = """
CREATE TABLE assets (
    asset_id    TEXT PRIMARY KEY,
    asset_name  TEXT NOT NULL,
    asset_type  TEXT NOT NULL,
    ops         TEXT NOT NULL,          -- comma-separated operations the line can run
    run_state   TEXT NOT NULL,          -- running | idle | down
    lockout     INTEGER NOT NULL,       -- safety tag / LOTO
    rate_kmh    REAL NOT NULL,          -- sustained throughput km/h
    cap_h       REAL NOT NULL,          -- max continuous-run window before mandatory PM
    oee         REAL NOT NULL
);
CREATE TABLE asset_health (
    asset_id        TEXT PRIMARY KEY REFERENCES assets(asset_id),
    health_score    INTEGER NOT NULL,   -- 0-100 condition
    vibration_trend TEXT NOT NULL,      -- stable | rising
    pm_due_days     INTEGER NOT NULL,   -- negative = overdue
    open_wo_count   INTEGER NOT NULL
);
CREATE TABLE vibration_readings (
    asset_id   TEXT REFERENCES assets(asset_id),
    day_offset INTEGER NOT NULL,        -- days before today
    value_mm_s REAL NOT NULL,
    threshold  REAL NOT NULL
);
CREATE TABLE oee_history (
    asset_id TEXT REFERENCES assets(asset_id),
    shift    INTEGER NOT NULL,
    oee      REAL NOT NULL
);
CREATE TABLE parts (
    part_key    TEXT PRIMARY KEY,
    part_family TEXT NOT NULL
);
CREATE TABLE quality_status (
    part_key   TEXT PRIMARY KEY REFERENCES parts(part_key),
    cpk        REAL NOT NULL,           -- capability on attenuation + cladding geometry
    spc_alerts INTEGER NOT NULL,
    open_ncrs  INTEGER NOT NULL,
    scrap_pct  REAL NOT NULL,
    reg_hold   INTEGER NOT NULL         -- customer qualification hold
);
CREATE TABLE materials (
    part_key   TEXT PRIMARY KEY REFERENCES parts(part_key),
    on_hand_km REAL NOT NULL,
    lead_days  INTEGER NOT NULL
);
CREATE TABLE customers (
    customer TEXT PRIMARY KEY,
    tier     TEXT NOT NULL
);
CREATE TABLE work_orders (
    order_id TEXT PRIMARY KEY,
    part_key TEXT NOT NULL REFERENCES parts(part_key),
    op       TEXT NOT NULL,             -- draw | spool | test | split | respool
    qty_km   INTEGER NOT NULL,
    due_days INTEGER NOT NULL,
    customer TEXT NOT NULL REFERENCES customers(customer)
);
"""


def build_orders(rng: random.Random) -> list[tuple]:
    """Mirror the demo's generateOrders(): balanced commit/escalate/reject mix."""
    counter = 4471
    orders: list[tuple] = []

    def push(part: str, qty_pool: list[int], due_pool: list[int]) -> None:
        nonlocal counter
        cust = rng.choice(CUSTS)
        orders.append((
            f"WO-{counter}", part, rng.choice(OP_POOL),
            rng.choice(qty_pool), rng.choice(due_pool), cust[0],
        ))
        counter += 1

    # ~16 clean -> COMMIT
    for _ in range(16):
        push("SMF-G652D" if rng.random() < 0.6 else "BIF-G657A2", [120, 160, 200], [4, 5, 6, 7, 8])
    # ~8 marginal (Quality objects) -> ESCALATE
    for _ in range(8):
        push("MMF-OM4", [120, 160, 200, 240, 300], [3, 4, 5, 6])
    # ~8 hard-veto -> REJECT (ULL only vetoes above its 140 km buffer)
    veto_parts = ["PMF-SPEC", "DSF-SPEC", "ULL-G654E"]
    for i in range(8):
        part = veto_parts[i % len(veto_parts)]
        push(part, [160, 200, 240, 300] if part == "ULL-G654E" else [120, 160, 200, 240], [2, 3, 4, 5])

    rng.shuffle(orders)
    return orders


def seed(db_path: Path, rng_seed: int = 42) -> None:
    rng = random.Random(rng_seed)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    with sqlite3.connect(db_path) as con:
        con.executescript(SCHEMA)

        for aid, name, typ, ops, health, vib, pm, wo, lock, run, oee, rate, cap in ASSETS:
            con.execute("INSERT INTO assets VALUES (?,?,?,?,?,?,?,?,?)",
                        (aid, name, typ, ops, run, lock, rate, cap, oee))
            con.execute("INSERT INTO asset_health VALUES (?,?,?,?,?)", (aid, health, vib, pm, wo))
            # 30 days of vibration history consistent with the trend
            base = 2.0 + (100 - health) * 0.03
            for day in range(30, 0, -1):
                drift = (30 - day) * 0.02 if vib == "rising" else 0.0
                con.execute("INSERT INTO vibration_readings VALUES (?,?,?,?)",
                            (aid, day, round(base + drift + rng.uniform(-0.15, 0.15), 2), 4.5))
            # recent OEE per shift around the nominal value
            for shift in range(1, 22):
                con.execute("INSERT INTO oee_history VALUES (?,?,?)",
                            (aid, shift, round(min(0.99, max(0.3, oee + rng.uniform(-0.05, 0.05))), 3)))

        for key, family, cpk, spc, ncr, scrap, avail, lead, hold in PARTS:
            con.execute("INSERT INTO parts VALUES (?,?)", (key, family))
            con.execute("INSERT INTO quality_status VALUES (?,?,?,?,?,?)",
                        (key, cpk, spc, ncr, scrap, hold))
            con.execute("INSERT INTO materials VALUES (?,?,?)", (key, avail, lead))

        for cust, tier in CUSTS:
            con.execute("INSERT INTO customers VALUES (?,?)", (cust, tier))

        con.executemany("INSERT INTO work_orders VALUES (?,?,?,?,?,?)", build_orders(rng))
        con.commit()


if __name__ == "__main__":
    from config import settings

    seed(settings.db_path)
    print(f"Seeded {settings.db_path}")
