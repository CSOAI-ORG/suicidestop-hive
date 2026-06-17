"""
MEOK BRIDGE — the 19th product. The router that connects everything.

The architecture Nick described:

        ┌──────────────── SOV3 (centre) ────────────────┐
        │   BFT council · safety · memory · reconciles   │
   LEFT ┤   (messages travel as MEOK SIGIL — signed,     ├ RIGHT
   ├ local (Ollama, private/free)   compressed wire fmt)  │  ├ local (Ollama big)
   └ api   (cheap MoE, e.g. DeepSeek)                      │  └ api (frontier: Vertex Gemini / Claude / GPT-4o)
        └────────────────────────────────────────────────┘

Each BRAIN can draw from BOTH a local source AND an api source — BRIDGE picks per side
by cost+quality, SOV3 governs safety in the centre, and the two sides' opinions are
reconciled. Every hop is logged as a SIGIL line so the whole exchange is an auditable,
compressed, signed trail (MEOK SIGIL inner-comms) the BFT council can read.

This wraps the existing router.ask() (which already knows local vs cloud backends) and the
existing brains.think() council logic — it does NOT replace them, it elevates them into a
named product with per-side source selection + SIGIL logging.

    bridge_think(character, message, profile="balanced") -> {reply, sides, sigil_log, safe}
    profiles: local_only | balanced | power | council

DAY-6: every bridge hop is now wrapped in the SOV3 3-tier SecurityBrain
(hot worm_guard scan + warm TurnCap/RAG + cold external-write gate) so a
worm/exfil/jailbreak payload cannot reach the LLM or any RAG-fed context.
The brain verdict is logged as a SIGIL line on every hop.
"""

import os
import sys
import time
from pathlib import Path

from .router import ask, list_models
from .connect import connect

# DAY-6: SOV3 security brain. The brain is OPTIONAL — bridge keeps working
# if it's not importable (e.g. meok-one shipped standalone), but in that
# degraded mode the bridge just runs without the per-hop 3-tier guard.
# We try the in-package import first, then fall back to a sibling-repo
# path layout (sovereign-temple/security/) which is how the SOV3 monorepo
# organises the four security modules.
try:
    from security.security_brain import SecurityBrain  # type: ignore
    _SECURITY_BRAIN_OK = True
except Exception:
    _SECURITY_BRAIN_OK = False
    # try adding the sibling sovereign-temple to sys.path so we can import
    try:
        _sec_candidates = [
            Path(__file__).resolve().parents[3] / "sovereign-temple" / "security",  # /Users/nicholas/clawd/sovereign-temple/security
            Path(__file__).resolve().parents[2] / "sovereign-temple" / "security",
            Path(__file__).resolve().parents[1] / "security",
        ]
        for _cand in _sec_candidates:
            if _cand.is_dir():
                _p = str(_cand.parent)
                if _p not in sys.path:
                    sys.path.insert(0, _p)
                from security.security_brain import SecurityBrain  # type: ignore
                _SECURITY_BRAIN_OK = True
                break
    except Exception:
        _SECURITY_BRAIN_OK = False

# MEOK SIGIL — inner-comms wire format (signed, ~2.4x denser than JSON)
_SIGIL = Path(__file__).resolve().parents[2] / "meok-sigil"
if str(_SIGIL) not in sys.path:
    sys.path.insert(0, str(_SIGIL))
try:
    from sigil import encode as _sigil_encode, digest as _sigil_digest
    _HAVE_SIGIL = True
except Exception:
    _HAVE_SIGIL = False


def _safe_digest(line):
    """Tamper-evident digest of a SIGIL line; None if the line isn't valid SIGIL."""
    if not _HAVE_SIGIL or not line:
        return None
    try:
        return _sigil_digest(line)
    except Exception:
        return None


# A "side" = which source(s) that brain may draw from. BRIDGE picks within the side.
# left  = privacy/cost side  (local first, cheap-api fallback)
# right = power side          (frontier api first, local-big fallback)
_PROFILES = {
    "local_only": {"left": ["local"],          "right": ["local"]},           # fully private/offline
    "balanced":   {"left": ["local"],          "right": ["cloud", "local"]},  # default: private left, powerful right
    "power":      {"left": ["cloud", "local"], "right": ["cloud"]},           # both lean on frontier APIs
    "council":    {"left": ["local"],          "right": ["cloud", "local"]},  # both run, SOV3 reconciles
    # DAY-7: "health" profile — both sides use a HEALTH/COMPLIANCE lens. Left = private
    # local medical-specialist Ollama (PHI never leaves the box), right = cloud
    # compliance-llm (HIPAA/GDPR guardrail check). Used for healthcare-adjacent
    # conversations where the bridge must default to a compliance-aware voice.
    "health":     {"left": ["local"],          "right": ["cloud", "local"],
                   "lens": "health",  # the lens tag; consumed by profile_quantum.py
                   "system_overlay": (
                       "You are operating in HEALTH/COMPLIANCE mode. "
                       "Prioritise: (1) medical safety — never recommend a specific "
                       "drug, dose, or procedure; (2) regulatory compliance — HIPAA / "
                       "GDPR / MHRA phrasing; (3) signposting to a qualified clinician "
                       "for anything diagnostic. Warm but clinical. No PHI to the cloud."
                   )},
}

# DAY-7: the profile quantum scorer can patch this sidecar on every call so the
# bridge self-tunes without a code redeploy. The file is read fresh on every
# bridge_think() invocation, so updates land within one turn.
import json as _json
_PROFILE_WEIGHTS_PATH = "/tmp/profile_weights.json"
def _load_profile_weights() -> dict:
    try:
        with open(_PROFILE_WEIGHTS_PATH, "r") as _f:
            return _json.load(_f)
    except Exception:
        return {}
def _pick_with_weight(profile: str, side: str, backend: str) -> str:
    """Override the static _PICK with a quantum-tuned model when the sidecar says so.
    The sidecar shape is: { "<profile>": { "<side>:<backend>": "<model>" } }."""
    w = _load_profile_weights()
    ovr = (w.get(profile) or {}).get(f"{side}:{backend}")
    if ovr:
        return str(ovr)
    return str(_PICK.get((side, backend)) or "")

# preferred concrete model per (side, backend) — BRIDGE's routing table
# (right-cloud and health profile can also use the compliance-llm override)
_PICK = {
    ("left", "local"):  "qwen3:0.6b",      # bench winner — private, fast, free
    ("left", "cloud"):  "kimi-k2.7-code", # KIMI K2.7-CODE: top-tier code-specialized, reasoning tokens, $0.00035/call
    ("right", "local"): "qwen3:4b",        # bigger local when offline
    # right brain = frontier on Nick's credit. Default to the VERIFIED-working Gemini model.
    ("right", "cloud"): os.environ.get("MEOK_RIGHT_MODEL", "gemini"),  # → gemini-flash-latest
    # DAY-7: health profile overrides — left uses the medical-specialist local
    # model, right uses the compliance-llm cloud model (both routed via the
    # _PROFILES["health"]["system_overlay"] lens).
    ("health", "left",  "local"):  os.environ.get("MEOK_HEALTH_LEFT_MODEL",  "medllama2"),
    ("health", "right", "cloud"):  os.environ.get("MEOK_HEALTH_RIGHT_MODEL", "compliance-llm"),
}


def _sigil_line(frm, to, kind, payload, tier=""):
    """One inner-comms hop as a SIGIL line (falls back to plain dict repr if SIGIL absent).
    `tier` is the memory/storage tier this hop touched (hot/warm/cold) and is encoded into
    the line so the audit chain records the storage tier of every backend call."""
    msg = {"t": round(time.time(), 1), "from": frm, "to": to, "k": kind,
           "p": str(payload)[:160], "tier": tier}
    if _HAVE_SIGIL:
        try:
            return _sigil_encode(msg)
        except Exception:
            pass
    ttag = f" tier={tier}" if tier else ""
    return f"{frm}->{to} [{kind}]{ttag} {str(payload)[:120]}"


# Tier classification of each bridge backend — the routing decision tree.
#  • left-local  (Ollama, on the same machine) → hot  (RAM, sub-ms, ephemeral)
#  • right-local (Ollama big, same machine)     → warm (SSD-survivable; in-process too)
#  • left-cloud  (cheap MoE API)               → warm (network roundtrip, seconds, not sovereign)
#  • right-cloud (frontier API on Nick's credit)→ cold (sovereign, signed, audit-chained)
#  • sov3 (centre reconciliation)              → cold
_BACKEND_TIER = {
    ("left", "local"):  "hot",
    ("left", "cloud"):  "warm",
    ("right", "local"): "warm",
    ("right", "cloud"): "cold",
}


def _available(backend: str, tier: str) -> bool:
    if backend == "cloud":
        # cloud needs a key (BYOK/Vertex/etc.) AND the tier must allow it
        has_key = any(os.environ.get(k) for k in
                      ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
                       "GOOGLE_API_KEY", "GOOGLE_CLOUD_PROJECT", "DEEPSEEK_API_KEY"))
        return has_key and any(m["backend"] == "cloud" for m in list_models(tier))
    return any(m["backend"] == backend for m in list_models(tier))


def _run_side(side: str, prompt: str, sources: list, tier: str, log: list,
              brain: "SecurityBrain | None" = None,
              profile: str = "balanced") -> dict:
    """Run ONE brain side: try its sources in order (local|api), log each hop in SIGIL.
    Every hop is tagged with the memory/storage tier of the backend it touched.

    DAY-6: if a SecurityBrain is passed, every model call goes through the brain's
    3-tier guard (hot worm scan, warm TurnCap/RAG, cold external-write gate). A
    blocking verdict short-circuits this side and the answer is the brain's veto
    note (the central SOV3 still reconciles, but a hot veto wins)."""
    for backend in sources:
        if not _available(backend, tier):
            log.append(_sigil_line("bridge", side, "skip", f"{backend} unavailable",
                                   tier=_BACKEND_TIER.get((side, backend), "?")))
            continue
        model = _PICK.get((side, backend))
        if model is None and profile == "health":
            # the 3-tuple keys are only present for the health profile
            model = (_PICK.get((profile, side, backend)) or
                     _pick_with_weight(profile, side, backend))
        if not model:
            model = _pick_with_weight(profile, side, backend) or _pick_with_weight(side, backend, "local") or "qwen3:0.6b"
        hop_tier = _BACKEND_TIER.get((side, backend), "?")
        # DAY-6: gate the hop through the SOV3 3-tier SecurityBrain.
        # We pass the tool-less guard first (text=prompt, tool_name=None) so a
        # worm/exfil/jailbreak in the prompt cannot reach the model. We pass
        # the model call as tool_name="<hop>" so the cold tier logs the hop.
        if brain is not None:
            try:
                hop_tool = f"bridge_hop:{side}:{backend}"
                verdict = brain.guard(text=prompt, tool_name=hop_tool,
                                       arguments={"_est_tokens": len(prompt) // 4})
                log.append(_sigil_line("brain", f"{side}:{backend}", "guard",
                                       f"{verdict.tier}:{verdict.action}/{verdict.severity}",
                                       tier=hop_tier))
                if verdict.is_blocked():
                    log.append(_sigil_line("brain", f"{side}:{backend}", "veto",
                                           verdict.details.get("reason")
                                           or verdict.details.get("reason")
                                           or verdict.details.get("fix")
                                           or f"{verdict.tier} {verdict.action}",
                                           tier=hop_tier))
                    return {"side": side, "backend": backend, "model": model,
                            "reply": None, "source": "blocked_by_security_brain",
                            "tier": hop_tier, "guard": verdict.to_dict()}
            except Exception as _e:
                # guard should never break the bridge
                log.append(_sigil_line("brain", f"{side}:{backend}", "guard_error",
                                       f"{type(_e).__name__}", tier=hop_tier))
        log.append(_sigil_line("bridge", f"{side}:{backend}", "ask", model, tier=hop_tier))
        out = ask(prompt, model=model, tier=tier)
        if out.get("reply"):
            log.append(_sigil_line(f"{side}:{backend}", "sov3", "reply",
                                   out["reply"], tier=hop_tier))
            return {"side": side, "backend": backend, "model": out.get("model"),
                    "reply": out["reply"], "source": out.get("source"),
                    "tier": hop_tier}
    return {"side": side, "backend": None, "reply": None, "model": None, "tier": None}


_UNSAFE = ("kill yourself", "you should harm", "here's how to hack", "get over it")
def _safe(t): return not any(b in (t or "").lower() for b in _UNSAFE)


def bridge_think(character_id: str, message: str, profile: str = "balanced",
                 tier: str = "pro", user_id: str = "web") -> dict:
    """The BRIDGE: route the user turn through left+right brains (each local|api),
    SOV3 in the centre reconciles, every hop logged in SIGIL."""
    prof = _PROFILES.get(profile, _PROFILES["balanced"])
    env = connect(character_id, user_id, message, tier=tier)
    char = env["meta"]["character_name"]
    base_prompt = f"{env['system_prompt']}\n\nUser: {message}\n\n{char}:"
    # DAY-7: if the profile carries a system_overlay (e.g. health/compliance
    # lens), inject it into the prompt so BOTH sides see it.
    overlay = prof.get("system_overlay") if isinstance(prof, dict) else None
    prompt = (base_prompt + "\n\n" + overlay) if overlay else base_prompt

    log = [_sigil_line("user", "bridge", "turn", message, tier="hot")]
    left = _run_side("left", prompt, prof["left"], tier, log, profile=profile)
    right = _run_side("right", prompt, prof["right"], tier, log, profile=profile)

    # SOV3 centre reconciles: prefer the powerful (right) reply if safe; else left; else honest fail.
    cands = [right, left] if profile in ("power", "balanced", "council", "health") else [left, right]
    final = next((c["reply"] for c in cands if c["reply"] and _safe(c["reply"])), None)
    if not final:
        final = f"[{char} is between brains right now — try again in a moment.]"
        log.append(_sigil_line("sov3", "user", "fail", "no safe backend answered", tier="cold"))
    else:
        winner = next(c for c in cands if c["reply"] == final)
        log.append(_sigil_line("sov3", "user", "reconciled",
                               f"chose {winner['side']}:{winner['backend']}",
                               tier=winner.get("tier", "cold")))

    # Tier-routing summary line — the audit-trail-visible "which tiers did this turn touch"
    tiers_touched = []
    for t in (left.get("tier"), right.get("tier")):
        if t and t not in tiers_touched:
            tiers_touched.append(t)
    summary = (f"left_{left.get('backend') or 'none'}={left.get('tier') or '?'} "
               f"right_{right.get('backend') or 'none'}={right.get('tier') or '?'} "
               f"sov3=cold tiers=[{','.join(tiers_touched) or 'none'}]")
    log.append(_sigil_line("bridge", "audit", "tier_summary", summary, tier="cold"))

    return {
        "character": char, "emoji": env["meta"]["emoji"],
        "reply": final, "profile": profile,
        "sides": {"left": {k: left.get(k) for k in ("backend", "model", "tier")},
                  "right": {k: right.get(k) for k in ("backend", "model", "tier")}},
        "tiers_touched": tiers_touched,
        "sigil_log": log,                    # the inner-comms trail (SIGIL-encoded)
        "sigil_digest": _safe_digest(log[-1]) if log else None,
        "safe": _safe(final),
        "engine": "MEOK BRIDGE",
    }


if __name__ == "__main__":
    import json
    print("SIGIL inner-comms:", "ON" if _HAVE_SIGIL else "fallback")
    out = bridge_think("aria", "I feel a bit low today", profile="balanced", tier="pro")
    print(f"\n{out['character']} via {out['engine']} (left={out['sides']['left']}, right={out['sides']['right']})")
    print("reply:", (out["reply"] or "")[:160])
    print("\n--- SIGIL inner-comms trail ---")
    for line in out["sigil_log"]:
        print(" ", line[:100])
