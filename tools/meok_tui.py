#!/usr/bin/env python3
"""
MEOK — EXECUTION TUI.  The control tab for the King / 28 Queens / Honeycomb.

This is the hand-over of MEOK UX to a terminal console: you talk to the KING
(SOV3 sovereign), it routes to the right hive QUEEN (MoE + BFT), the answer comes
back, and the lesson is gossiped to the HONEYCOMB. Every execution is TRACED to a
JSONL (Langfuse-lite — full Langfuse needs Docker+Postgres, which won't fit the
16GB Mac; this gives the same visibility with zero infra).

    python3 tools/meok_tui.py

Commands:
    <message>          ask the King — it routes to the best hive queen
    /fan <message>     convene the top-3 queens, sovereign synthesizes
    /queen <d> <msg>   talk to one hive's queen directly (d = slug, e.g. grabhire)
    /hives             list the 28 hives the King governs
    /health            health of SOV3 + services + inference
    /trace [n]         last n execution traces (default 10) — the observability tab
    /honey [n]         last n honey drops sent to the honeycomb
    /audit <text>      MiniMax M3 adversarially audits a claim/plan (dual-agent)
    /reset  /quit
"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from meok_one.hive_king import king, route, hives  # noqa: E402
from meok_one.hive_queen import queen  # noqa: E402

TRACE = Path(__file__).resolve().parents[1] / "data" / "hive_traces.jsonl"
TRACE.parent.mkdir(exist_ok=True)

C = dict(reset="\033[0m", dim="\033[2m", cyan="\033[36m", mag="\033[35m",
         yel="\033[33m", grn="\033[32m", red="\033[31m", bold="\033[1m",
         indigo="\033[38;5;99m", gray="\033[38;5;245m", gold="\033[38;5;220m")

BANNER = f"""{C['gold']}{C['bold']}
   🤴  M E O K   ·   E X E C U T I O N   C O N S O L E
{C['reset']}{C['gray']}   King (SOV3) → 28 Queens (MoE+BFT) → Honeycomb · every call traced
   /hives  /health  /trace  /honey  /fan  /queen  /audit  /quit{C['reset']}
"""


def trace(kind, payload):
    """Langfuse-lite: append one execution record. Best-effort, never raises."""
    try:
        rec = {"ts": round(time.time(), 1), "kind": kind, **payload}
        with TRACE.open("a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
    except Exception:  # noqa: BLE001
        pass


def _read_traces(n):
    if not TRACE.exists():
        return []
    lines = TRACE.read_text().splitlines()[-n:]
    out = []
    for l in lines:
        try:
            out.append(json.loads(l))
        except json.JSONDecodeError:
            pass
    return out


def cmd_hives():
    hv = hives()
    print(f"{C['indigo']}{C['bold']}{len(hv)} hives governed by the King:{C['reset']}")
    for h in hv:
        print(f"  {C['gold']}👑 {h['slug']:<26}{C['reset']} {C['gray']}{(h['scope'] or '')[:70]}{C['reset']}")


def cmd_health():
    checks = [("SOV3 king/honeycomb :3101", "http://localhost:3101/health"),
              ("MEOK :3000", "http://localhost:3000"),
              ("Sovereign MCP :3100", "http://localhost:3100"),
              ("MEOK MCP :3102", "http://localhost:3102"),
              ("Ollama local :11434", "http://localhost:11434/api/tags")]
    for name, url in checks:
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                ok = r.status == 200
            print(f"  {C['grn']}● {C['reset']}{name}")
        except Exception:  # noqa: BLE001
            print(f"  {C['red']}● {C['reset']}{name} {C['gray']}(down){C['reset']}")


def cmd_trace(n):
    rows = _read_traces(n)
    if not rows:
        print(f"{C['gray']}no traces yet — run a query first.{C['reset']}")
        return
    print(f"{C['cyan']}{C['bold']}last {len(rows)} executions:{C['reset']}")
    for r in rows:
        when = time.strftime("%H:%M:%S", time.localtime(r.get("ts", 0)))
        if r["kind"] == "king":
            print(f"  {C['gray']}{when}{C['reset']} 🤴 → {C['gold']}{','.join(r.get('routed_to', []))}{C['reset']} "
                  f"{C['gray']}({r.get('latency_s')}s) {C['reset']}{(r.get('q') or '')[:50]}")
        elif r["kind"] == "queen":
            print(f"  {C['gray']}{when}{C['reset']} 👑 {C['gold']}{r.get('hive')}{C['reset']} "
                  f"{C['gray']}{r.get('engine','')} · safe={r.get('safe')} ({r.get('latency_s')}s){C['reset']}")
        elif r["kind"] == "audit":
            print(f"  {C['gray']}{when}{C['reset']} 🔍 M3 audit {C['gray']}({r.get('latency_s')}s){C['reset']}")


def cmd_honey(n):
    rows = [r for r in _read_traces(200) if r.get("honey")][-n:]
    if not rows:
        print(f"{C['gray']}no honey yet.{C['reset']}")
        return
    print(f"{C['gold']}{C['bold']}🍯 last {len(rows)} honey drops → honeycomb:{C['reset']}")
    for r in rows:
        h = r["honey"]
        print(f"  {C['gold']}{h.get('hive')}{C['reset']}: {C['gray']}{(h.get('answer') or '')[:80]}{C['reset']}")


def m3_audit(text):
    body = json.dumps({"model": "minimax-m3:cloud", "stream": False, "messages": [
        {"role": "system", "content": "You are MiniMax M3, the AUDITOR (Claude builds, "
         "you audit, Nick is sovereign). Be adversarial and concrete: find the flaw or "
         "unverified claim. If sound, say so briefly. No flattery."},
        {"role": "user", "content": text}]}).encode()
    # M3 is a LOCAL Mac model — force localhost regardless of VM env.
    url = "http://localhost:11434/api/chat"
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            out = json.loads(r.read().decode())["message"]["content"]
    except Exception as e:  # noqa: BLE001
        out = f"[M3 unreachable: {type(e).__name__}]"
    trace("audit", {"q": text[:120], "latency_s": round(time.time() - t, 1)})
    return out


def main():
    print(BANNER)
    while True:
        try:
            msg = input(f"{C['gold']}{C['bold']}meok ›{C['reset']} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{C['gray']}bye.{C['reset']}")
            return
        if not msg:
            continue
        if msg in ("/quit", "/q", "/exit"):
            print(f"{C['gray']}bye.{C['reset']}")
            return
        if msg == "/hives":
            cmd_hives(); continue
        if msg == "/health":
            cmd_health(); continue
        if msg.startswith("/trace"):
            cmd_trace(int((msg.split() + ["10"])[1]) if msg.split()[1:] else 10); continue
        if msg.startswith("/honey"):
            cmd_honey(int((msg.split() + ["10"])[1]) if msg.split()[1:] else 10); continue
        if msg.startswith("/audit"):
            text = msg[len("/audit"):].strip()
            print(f"{C['mag']}{C['bold']}🔍 M3 audit ›{C['reset']}\n{m3_audit(text)}"); continue
        if msg.startswith("/queen"):
            parts = msg.split(maxsplit=2)
            if len(parts) < 3:
                print(f"{C['gray']}usage: /queen <slug> <message>{C['reset']}"); continue
            slug, q = parts[1], parts[2]
            t = time.time()
            r = queen(slug, q, brain="council", do_gossip=True)
            r["latency_s"] = round(time.time() - t, 1)
            trace("queen", {"hive": slug, "q": q[:80], "engine": r.get("engine"),
                            "safe": r.get("safe"), "latency_s": r["latency_s"], "honey": r.get("honey")})
            print(f"{C['gold']}👑 {slug}{C['reset']} {C['gray']}{r.get('engine')}{C['reset']}\n{r.get('reply')}")
            continue
        # default OR /fan: ask the King
        fan = msg.startswith("/fan")
        q = msg[len("/fan"):].strip() if fan else msg
        print(f"{C['gray']}🤴 routing…{C['reset']}")
        t = time.time()
        r = king(q, fan_out=fan, do_gossip=True)
        lat = round(time.time() - t, 1)
        trace("king", {"q": q[:80], "routed_to": r.get("routed_to"), "mode": r.get("mode"),
                       "latency_s": lat})
        for qa in r.get("queens", []):
            trace("queen", {"hive": qa.get("hive"), "engine": qa.get("engine"),
                            "safe": qa.get("safe"), "latency_s": lat})
        routed = ", ".join(r.get("routed_to", [])) or "—"
        print(f"{C['gold']}🤴 → 👑 {routed}{C['reset']} {C['gray']}({r.get('mode')}, {lat}s){C['reset']}")
        print(r.get("reply"))


if __name__ == "__main__":
    main()
