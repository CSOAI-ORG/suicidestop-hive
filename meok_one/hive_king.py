"""
MEOK ONE — THE KING: SOV3 the sovereign, talking to the 28 hive queens.

Topology (Nick's model, grounded):

    👤 you / user / agent
            │
        🤴 KING = SOV3 the sovereign  (one mouth you talk to)
            │   "which hive(s) should answer this?"  ← thin, stateless routing
     ┌──────┼──────┬───────── … ×28
     ▼      ▼      ▼
   👑meok  👑grab  👑koi   queens = hive_queen.queen(domain)  (MoE + BFT)
     └──────┴──────┴── all deposit honey ──▶ 🍯 HONEYCOMB = SOV3 memory

The king IS the sovereign (SOV3 identity), but its ROUTING is kept thin and stateless
so a SOV3 memory/VM wobble can't stop it picking a queen. Two modes:

    route(message)              -> pick the most relevant hive(s) (a fast classifier)
    king(message, fan_out=...)  -> route, call the queen(s), (fan_out) convene + synthesize

Inference runs on the GCP VM (the fast box); SOV3 (king/honeycomb) runs on the Mac :3101.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FutureTimeout
from pathlib import Path

from .router import ask
from .hive_queen import queen, load_hive, _HIVE_ROOT

# Routing/synthesis model. With OpenRouter, use a fast cloud model (instant routing, no
# local model swap); else the resident local model (no Ollama swap on the constrained VM).
import os as _os
_CLASSIFIER_MODEL = "gemini-or" if _os.environ.get("OPENROUTER_API_KEY") else "llama3.2:3b"


def hives() -> list[dict]:
    """All hives the king governs, with their domain scope (from each stack.yml)."""
    out = []
    if not _HIVE_ROOT.is_dir():
        return out
    for d in sorted(_HIVE_ROOT.glob("*-hive")):
        slug = d.name[:-5]  # strip "-hive"
        cfg = load_hive(slug)
        out.append({"slug": slug, "scope": cfg.get("scope") or slug,
                    "tools": cfg.get("tools", [])})
    return out


def route(message: str, k: int = 1, model: str = _CLASSIFIER_MODEL, tier: str = "pro") -> list[str]:
    """Pick the k most relevant hive slugs for a message. Fast LLM classifier with a
    keyword fallback so routing never hard-fails (thin + resilient — the king must
    always be able to pick a queen even if the classifier model is down)."""
    hv = hives()
    if not hv:
        return []
    # Compact catalog: slug + first ~8 words of scope. The full scopes were ~560 input
    # tokens → ~60s CPU prompt-eval. Trimming to ~150 tokens cuts routing to ~10-15s.
    def _short(s):
        return " ".join((s or "").replace("\n", " ").split()[:8])
    catalog = "\n".join(f"{h['slug']}: {_short(h['scope'])}" for h in hv)
    prompt = (f"Route this message to the ONE best MEOK hive. Reply with ONLY the slug.\n\n"
              f"{catalog}\n\nMESSAGE: {message}\nSLUG:" if k == 1 else
              f"Choose the {k} most relevant hive slugs (comma-separated, slugs only).\n\n"
              f"{catalog}\n\nMESSAGE: {message}\nSLUGS:")
    r = ask(prompt, model=model, tier=tier, max_tokens=24)
    slugs = [s.strip().lower() for s in (r.get("reply") or "").replace("\n", ",").split(",")]
    valid = {h["slug"] for h in hv}
    picked = [s for s in slugs if s in valid][:k]
    if not picked:
        # Near-miss: the classifier often returns a close variant ("koikeeper-hive",
        # or just "koi"). Accept it if it cleanly maps to exactly one valid slug by
        # substring containment — beats dropping a basically-correct answer to keyword.
        for s in slugs:
            if not s:
                continue
            cand = [v for v in valid if (s in v or v in s)]
            if len(cand) == 1 and cand[0] not in picked:
                picked.append(cand[0])
                if len(picked) >= k:
                    break
    if picked:
        return picked[:k]
    # Keyword fallback (classifier down/empty): score by word overlap, weighting a hit
    # on the slug name 3× a hit in the (longer, noisier) scope text so the most on-topic
    # hive wins instead of whichever scope happens to share common words.
    words = {w for w in message.lower().split() if len(w) > 2}

    def _score(h):
        slug_words = set(h["slug"].lower().replace("-", " ").split())
        scope_words = set((h.get("scope") or "").lower().split())
        return 3 * len(slug_words & words) + len(scope_words & words)

    scored = sorted(hv, key=_score, reverse=True)
    return [scored[0]["slug"]] if scored and _score(scored[0]) > 0 else (
        [scored[0]["slug"]] if scored else [])


def king(message: str, fan_out: bool = False, k: int = 3, brain: str = "council",
         do_gossip: bool = True, quorum: int = 3, deadline: float = 90.0,
         fan_brain: str = "right") -> dict:
    """The sovereign answers by convening the right queen(s).

    fan_out=False : route to the single best hive, return its queen's answer (full `brain`,
                    default council — single-hive answers keep BFT depth).
    fan_out=True  : convene the top-k queens, then the sovereign synthesizes ONE answer.
                    Each queen uses the lighter `fan_brain` (default "right" = one fast cloud
                    pass) instead of a full council — running k full BFT councils in parallel
                    was ~2-3min; the sovereign SYNTHESIS step already provides the cross-queen
                    deliberation, so per-queen council depth is redundant here.
    do_gossip     : each queen records its lesson UP to the SOV3 honeycomb.
    deadline      : overall wall-clock budget (seconds) for convening the queens. A queen
                    that hangs (not just errors) is abandoned so the king always returns.
    """
    targets = route(message, k=k if fan_out else 1)
    if not targets:
        return {"king": "SOV3 sovereign", "routed_to": [], "reply":
                "[king couldn't route — no hives found]", "queens": []}

    # Fan-out queens run a fast single brain (synthesis deliberates); single-hive keeps depth.
    per_queen_brain = fan_brain if fan_out else brain

    def _call(slug: str) -> dict:
        # One queen erroring (model/network/VM wobble) must not take down the king —
        # especially in fan_out where k queens are consulted. Capture failure non-fatally.
        try:
            a = queen(slug, message, brain=per_queen_brain, do_gossip=do_gossip, quorum=quorum)
            return {"hive": slug, "reply": a.get("reply"), "engine": a.get("engine"),
                    "safe": a.get("safe"), "governance": a.get("governance")}
        except Exception as e:
            return {"hive": slug, "reply": None, "engine": None, "safe": True,
                    "governance": None, "error": type(e).__name__}

    # Convene queens in parallel, bounded by an overall deadline (closes Bug#4: king had
    # no overall deadline + ran fan-out sequentially, so 3 queens took 3× one queen's time
    # and a single hang blocked everything). Results collected in target order.
    by_slug: dict[str, dict] = {}
    ex = ThreadPoolExecutor(max_workers=max(1, len(targets)))
    try:
        futs = {slug: ex.submit(_call, slug) for slug in targets}
        end = time.monotonic() + deadline
        for slug, fut in futs.items():
            try:
                by_slug[slug] = fut.result(timeout=max(0.0, end - time.monotonic()))
            except _FutureTimeout:
                by_slug[slug] = {"hive": slug, "reply": None, "engine": None,
                                 "safe": True, "governance": None, "error": "timeout"}
            except Exception as e:
                by_slug[slug] = {"hive": slug, "reply": None, "engine": None,
                                 "safe": True, "governance": None, "error": type(e).__name__}
    finally:
        # Don't block on a hung queen's thread; let it finish its gossip in the background.
        ex.shutdown(wait=False)
    answers = [by_slug[slug] for slug in targets]

    ok = [a for a in answers if a.get("reply")]

    if not fan_out:
        a = answers[0]
        reply = a["reply"] or f"[{a['hive']} queen unavailable: {a.get('error', 'no reply')}]"
        return {"king": "SOV3 sovereign", "routed_to": targets, "mode": "route",
                "reply": reply, "queens": answers}

    # fan-out: the sovereign synthesizes the queens' answers into one. Synthesize only
    # over queens that actually answered; if none did, surface that honestly.
    if not ok:
        return {"king": "SOV3 sovereign", "routed_to": targets, "mode": "fan_out",
                "reply": "[all routed queens were unavailable]", "queens": answers}
    brief = "\n\n".join(f"[{x['hive']} queen]: {x['reply']}" for x in ok)
    synth = ask(f"You are SOV3, the sovereign over MEOK's hives. {len(ok)} hive "
                f"queens answered the user. Synthesize ONE clear, safe answer for the "
                f"user, noting which hive each insight came from.\n\nUSER: {message}\n\n"
                f"QUEEN ANSWERS:\n{brief}\n\nSOVEREIGN SYNTHESIS:",
                model=_CLASSIFIER_MODEL, tier="pro", max_tokens=400)
    return {"king": "SOV3 sovereign", "routed_to": targets, "mode": "fan_out",
            "reply": synth.get("reply") or brief, "queens": answers}


def _cli():
    """Console entry point: `meok-king "<message>" [--fan]`."""
    import sys
    msg = sys.argv[1] if len(sys.argv) > 1 else "I need to tip soil at a construction site — what permits?"
    fan = "--fan" in sys.argv
    print(f"=== 🤴 KING (fan_out={fan}) ===\nuser: {msg}\n")
    res = king(msg, fan_out=fan)
    print("routed_to:", res["routed_to"], "| mode:", res.get("mode"))
    print("\nreply:\n", (res["reply"] or "")[:600])
    print("\n--- queens consulted ---")
    for q in res["queens"]:
        print(f"  👑 {q['hive']}: {q['engine']} | safe={q['safe']}")


if __name__ == "__main__":
    _cli()
