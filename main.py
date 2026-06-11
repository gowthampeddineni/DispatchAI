"""DispatchAI multi-agent backend — single CLI entry point.

    python main.py seed            # create + seed data/dispatchai.db
    python main.py serve           # start the FastAPI/WebSocket server (+ demo at /)
    python main.py demo [ORDER_ID] # run one negotiation in the terminal
"""
from __future__ import annotations

import argparse
import asyncio
import sys


def cmd_seed(_: argparse.Namespace) -> None:
    from config import settings
    from data.seed_db import seed

    seed(settings.db_path)
    print(f"Seeded {settings.db_path}")


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    from config import settings
    from data.seed_db import seed

    if not settings.db_path.exists():
        seed(settings.db_path)
        print(f"Seeded {settings.db_path}")
    mode = "LLM live" if settings.llm_enabled else "deterministic rules (no OPENAI_API_KEY)"
    print(f"DispatchAI backend on http://{args.host or settings.host}:{args.port or settings.port}"
          f"  ·  agents: {mode}")
    print("Open the demo at /  ·  WebSocket at /ws")
    uvicorn.run("server.app:app", host=args.host or settings.host,
                port=args.port or settings.port, log_level="info")


def cmd_demo(args: argparse.Namespace) -> None:
    """One full dispatch request through the orchestrator, printed live."""
    from config import settings
    from data.seed_db import seed

    if not settings.db_path.exists():
        seed(settings.db_path)

    import tools
    from domain import Order, Proposal
    from orchestrator import plan_slot, run_negotiation

    async def main() -> None:
        queue = await tools.call_tool("list_work_orders")
        if args.order_id:
            row = next((o for o in queue if o["id"] == args.order_id), None)
            if row is None:
                sys.exit(f"Order {args.order_id} not in queue. Try one of: "
                         + ", ".join(o["id"] for o in queue[:8]) + " …")
        else:
            row = queue[0]
        order = Order(**row)
        asset_id, start_hr, dur_h = await plan_slot(order, [])
        proposal = Proposal(order=order, part_key=order.part, asset_id=asset_id,
                            start_hr=start_hr, dur_h=dur_h)
        print(f"\n{order.id} · {order.op.upper()} · {order.qty} km · {order.cust} "
              f"→ {asset_id} @ t+{start_hr:g}h ({dur_h:g}h)\n")

        async def emit(etype: str, agent_id: str | None, payload: dict) -> None:
            if etype == "agent_position":
                tag = "HARD VETO" if payload["veto"] else payload["pos"]
                print(f"  [{agent_id:>5}] {tag:<9} {payload['why']}")
                print(f"          ⛏ {payload['tool']}")
            elif etype == "orchestrator_note":
                fam = payload["familiarity"]
                print(f"\n  [orch ] {payload['note']}")
                print(f"          familiarity {fam['zone'].upper()} (z={fam['z']:.2f}) "
                      f"· confidence {int(payload['confidence'] * 100)}%")
            elif etype == "verdict" and payload.get("suggested_fix"):
                print(f"          💡 {payload['suggested_fix']}")

        verdict = await run_negotiation(proposal, emit, "cli-demo")
        print(f"\n  ==> {verdict.outcome}  ({verdict.acc} accept · {verdict.con} concede "
              f"· {verdict.obj} object)\n")

    asyncio.run(main())


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dispatchai", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed", help="create + seed the SQLite database").set_defaults(fn=cmd_seed)
    sp = sub.add_parser("serve", help="start the WebSocket server + demo")
    sp.add_argument("--host", default=None)
    sp.add_argument("--port", type=int, default=None)
    sp.set_defaults(fn=cmd_serve)
    dp = sub.add_parser("demo", help="run one negotiation in the terminal")
    dp.add_argument("order_id", nargs="?", default=None)
    dp.set_defaults(fn=cmd_demo)
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    args.fn(args)
