"""
MEOK ONE — HIVE QUEEN: one proven engine, any hive.

Each MEOK business is a HIVE (hive-staging/<domain>-hive/stack.yml). Nick's model:
each hive has a QUEEN that is "an MCP-based MoE with our BFT", and SOV3 is the
honeycomb / honey-collector — the queen of queens that gathers what every hive learns.

The key integration decision (supersedes the evoagentx scaffold in hive-staging):
a queen is NOT a new 7-layer stack. A queen IS this meok-one engine, parameterised by
the hive's stack.yml. So "28 queens" = 28 config files on 1 battle-tested engine, not
28 unbuilt evoagentx stacks.

    MoE routing    = router.ask / brains.think across the hive's model roster
    BFT governance = sovereign.sovereign_council (the 12 lenses, safety-veto + vote)
    safe tools     = tunnels.safe_call, scoped to the hive's own MCPs (L5) + shared MEOK
    honey          = each interaction's lesson recorded UP to SOV3 (the honeycomb)

    load_hive(domain)                         -> hive config (roster, tools, palette, tier)
    queen(domain, message, brain=..., ...)    -> {domain, reply, safe, governance, honey, ...}

Runs FREE on this Mac: roster defaults to local Ollama (m3 = minimax-m3:cloud,
gemma4:e4b). No OpenRouter key required for a real BFT-of-MoEs deliberation.
"""
from __future__ import annotations

import json
from pathlib import Path

import os
import re
import urllib.request
from .brains import think
from .sovereign import sovereign_council
from . import tunnels
from . import tool_gateway as gw
from . import sigil
from . import telemetry

# The honeycomb (SOV3) runs as its own process on :3101 — not importable into this
# engine — so honey is delivered to it over MCP/HTTP, not in-process. Localhost on the VM.
_SOV3_MCP = os.environ.get("SOV3_MCP", "http://localhost:3101/mcp")


def _deliver_to_sov3(sigil_line: str, hive: str) -> dict:
    """POST one honey drop to the honeycomb's record_memory over MCP. Honey channel is
    HARDCODED to record_memory — it can never be repurposed to fire another write."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "record_memory", "arguments": {
            "content": sigil_line, "memory_type": "hive_honey",
            "source_agent": f"{hive}-queen", "importance": 0.6,
            "tags": ["hive", hive, "honey"]}}}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(_SOV3_MCP, data=data, headers={
        "Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read().decode()
        if "data:" in body:  # SSE framing
            body = [l[5:].strip() for l in body.splitlines() if l.startswith("data:")][-1]
        env = json.loads(body)
        return {"ok": "error" not in env, "delivered": True, "world": "sov3"}
    except Exception as e:  # noqa: BLE001 — honey is never lost; the SIGIL receipt persists
        return {"ok": False, "delivered": False, "error": type(e).__name__}


def _recall_from_sov3(hive: str, message: str, k: int = 3) -> list:
    """RETURN PATH (honeycomb→queen): pull this hive's prior honey relevant to the message.
    Memories are stored as compact SIGIL lines, so recall is already tiny — we just gloss
    the lesson out (the SIGIL `value`) rather than shipping JSON. Best-effort: [] on any error."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "query_memories", "arguments": {
            "query": message, "tags": ["honey", hive], "limit": k}}}
    try:
        req = urllib.request.Request(_SOV3_MCP, data=json.dumps(payload).encode(), headers={
            "Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read().decode()
        if "data:" in body:
            body = [l[5:].strip() for l in body.splitlines() if l.startswith("data:")][-1]
        env = json.loads(body)
        content = env.get("result", {}).get("content", [])
        text = content[0]["text"] if content and content[0].get("type") == "text" else "{}"
        mems = json.loads(text)
        rows = mems.get("memories", mems) if isinstance(mems, dict) else mems
        out = []
        own = f"honey;{hive}"   # this hive's SIGIL key — no cross-hive leakage
        for m in (rows or []):
            line = m.get("content", "") if isinstance(m, dict) else str(m)
            parts = line.split("|")
            # only THIS hive's honey (the shared 'honey' tag is OR-matched server-side, so
            # filter to our own key here — a hive must not recall another hive's lessons)
            if line.startswith("M|") and len(parts) > 2 and parts[1] == own:
                out.append(parts[2])
        return [s for s in out if s][:k]
    except Exception:  # noqa: BLE001
        return []

# Where the 28 scaffolded hives live (config = source of truth for a queen).
_HIVE_ROOT = Path.home() / "hive-staging"

# Default council roster. The GCP VM (meok-backend) is RAM-constrained: 7.8GB total,
# ~1.9GB free after SOV3+postgres+caddy+ollama — room for ONE 3B model resident. A
# multi-model roster forces unload/reload swaps per seat → councils take minutes.
# So default to a SINGLE resident model cycled across all council seats: the BFT
# diversity comes from the 12 LENS PROMPTS, not different weights. Stays loaded → fast.
# (Pass roster=[...] explicitly for true multi-model diversity on a bigger host.)
# When OpenRouter is configured, councils run on FAST FRONTIER cloud MoEs (genuine model
# diversity, sub-10s) — the real fix for slow CPU councils. Falls back to a single resident
# local model on RAM-constrained hosts when there's no key.
_CLOUD_ROSTER = ["gemini-or", "deepseek", "kimi"]   # fast diverse frontier MoEs via OpenRouter
_LOCAL_ROSTER = ["llama3.2:3b"]                       # single resident model (no-key fallback)
_DEFAULT_ROSTER = _CLOUD_ROSTER if os.environ.get("OPENROUTER_API_KEY") else _LOCAL_ROSTER
# Multi-model LOCAL option (needs a host with RAM for 2-3 resident 3B models):
_DIVERSE_ROSTER = ["qwen2.5:3b", "llama3.2:3b", "meok-sov3"]
# Free-local single-brain alternatives (this Mac, no key): m3 (minimax-m3:cloud), gemma4:e4b.
_FREE_LOCAL_ROSTER = ["m3", "gemma4:e4b"]

# Default endpoint character (connect() needs a known character; the hive supplies the
# DOMAIN identity on top). Override per hive via stack.yml -> L6.character later.
_DEFAULT_CHARACTER = "aria"


def load_hive(domain: str) -> dict:
    """Read a hive's stack.yml and distil the knobs a queen needs.

    `domain` may be 'meok', 'meok.ai', or 'grabhire' — we normalise to the
    hive-staging/<slug>-hive directory.
    """
    slug = domain.replace(".ai", "").replace(".org", "").replace(".", "-").strip("-")
    hive_dir = _HIVE_ROOT / f"{slug}-hive"
    # NOTE: stack.yml's `tier:` is a BUSINESS build-priority (flagship/governance/...),
    # NOT the engine's billing tier (local/free/pro/...). Keep them separate.
    cfg = {"domain": domain, "slug": slug, "found": hive_dir.is_dir(),
           "dir": str(hive_dir), "tier": "pro", "build_tier": "", "tools": [],
           "roster": list(_DEFAULT_ROSTER),
           "palette": "", "character": _DEFAULT_CHARACTER, "scope": ""}
    stack = hive_dir / "stack.yml"
    if not stack.exists():
        return cfg
    # Minimal YAML read without a yaml dep: pull the few scalars/lists we use. The
    # stack.yml schema is fixed (gen-hive.py), so targeted parsing is safe + dependency-free.
    text = stack.read_text()
    cfg["raw_stack"] = text
    # L5 tools (the hive's own MCPs) — lines under "tools:" as "- name"
    in_tools = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("tools:"):
            in_tools = True
            continue
        if in_tools:
            if s.startswith("- "):
                cfg["tools"].append(s[2:].strip())
            elif s and not s.startswith("#") and not line.startswith(" " * 6):
                in_tools = False
        if s.startswith("palette:"):
            cfg["palette"] = s.split(":", 1)[1].strip().strip('"')
        if s.startswith("scope:") and not cfg["scope"]:
            # first scope wins (L6 orchestration; the later L5 memory scope must not
            # overwrite it) and multi-line quoted blocks are captured in full.
            val = s.split(":", 1)[1].strip()
            block = [val.lstrip('"')]
            if val.startswith('"') and not (len(val) > 1 and val.endswith('"')):
                for cont in text.splitlines()[text.splitlines().index(line) + 1:]:
                    cs = cont.strip()
                    block.append(cs.rstrip('"'))
                    if cs.endswith('"'):
                        break
            cfg["scope"] = " ".join(b for b in block if b).strip().strip('"')
        if s.startswith("tier:") and not cfg["build_tier"]:
            cfg["build_tier"] = s.split(":", 1)[1].strip()
    return cfg


def _honey(domain: str, message: str, result: dict) -> dict:
    """The nectar a hive sends up to the honeycomb: slim, fixed-order, unambiguous.

    Hard caps keep it tiny (fewer tokens). Fixed field names (q/a/safe) so question and
    answer can never be swapped, and the direction is always hive→honeycomb.
    """
    return {
        "hive": domain,
        "q": (message or "")[:100],
        "a": (result.get("reply") or "")[:100],
        "safe": bool(result.get("safe")),
    }


def gossip(honey: dict) -> dict:
    """Carry one drop of honey UP to SOV3 (the honeycomb) — SIGIL-hardened.

    SECURITY + TINY: the lesson is first encoded as ONE compact SIGIL `M` opcode and
    hash-chained locally (receipt = sha256(prev+line)) — so the whole honey trail is
    tamper-evident and `sigil.verify_chain()`-able; no silent edit or injected memory
    survives. Then only that compact line (≈30 chars, not a ~600-char JSON blob) is
    sent up. NO-BACKWARDS: SIGIL strips the |/:/newline delimiters and the opcode is
    typed+directional (M = store, key=honey:<hive>), so up/down and read/write can't
    be confused. The honey channel is hardcoded to record_memory only — it can never
    be repurposed to fire an arbitrary write.
    """
    hive = honey.get("hive", "unknown")
    # 1) tamper-evident receipt FIRST — honey is never lost even if the honeycomb is down.
    rec = sigil.record({"op": "M", "key": f"honey:{hive}",
                        "value": honey.get("a", "")[:80], "salience": 0.6, "tier": "warm"})
    # 2) safety gate: a hardcoded honey write must never be prohibited (fail-closed).
    if gw.classify("record_memory") == "prohibited":
        return {"sigil": rec["line"], "receipt": rec["receipt"],
                "delivery": {"ok": False, "refused": "prohibited"}}
    # 3) deliver the compact SIGIL line to the honeycomb (SOV3 runs as its own process).
    delivery = _deliver_to_sov3(rec["line"], hive)

    # 4) publish anonymised telemetry for cross-hive learning (ASI-Evolve, etc.).
    # No raw Q/A is included — only aggregate-safe signals.
    telemetry.publish(
        hive=hive,
        event_type="queen_interaction",
        payload={
            "safe": bool(honey.get("safe")),
            "tags": ["honey", "queen", hive],
        },
    )

    return {"sigil": rec["line"], "receipt": rec["receipt"], "delivery": delivery}


def _clean_reply(reply: str, cfg: dict, brain: str) -> str:
    """Strip a leaked character-name prefix + (for non-council) a leading companion
    greeting, so the queen reads as a clean domain SME. (Extracted 2026-06-16 so the
    best-of-N path cleans every candidate identically.)"""
    _reply = reply or ""
    _nm = re.escape(cfg.get("character", "").strip().capitalize())
    if _nm:
        _reply = re.sub(rf"^\s*(As\s+{_nm}[,:]|{_nm}\s*[:\-—])\s*", "", _reply, count=1, flags=re.I)
    if brain != "council" and _reply:
        _comp = re.compile(
            r"\b(how are you|how're you|hope you|i'd love to|i'm curious|calm and kind|"
            r"truly doing|truly hope|before we (?:dive|begin)|how can i (?:help|assist)|"
            r"what brings you|warm(?:est)? (?:greetings|wishes))\b", re.I)
        _hello = re.compile(r"^\s*(?:oh[,!.\s]+)?(?:hello|hi|hey|greetings|welcome)\b", re.I)
        _parts = re.split(r"(?<=[.!?])\s+", _reply)
        _drop = 0
        for _s in _parts:
            if _comp.search(_s) or _hello.match(_s):
                _drop += 1
            else:
                break
        if _drop and len(" ".join(_parts[_drop:])) > 40:
            _reply = " ".join(_parts[_drop:]).lstrip()
    return _reply


def _ground_with_tool(domain: str, message: str, cfg: dict) -> "tuple[str, dict]":
    """Level-0 (2026-06-16): the queen ACTUALLY CALLS a tool through the safe gateway,
    instead of only string-interpolating tool names into the prompt (the #1 audit gap).

    Every call goes through tunnels.safe_call → tool_gateway: read-tier auto-executes,
    write needs a human confirm, prohibited is refused — and each call is SIGIL-audited.
    We try the hive's own declared tools first; whatever executes is injected as grounding.
    Returns (context_string, audit). Best-effort — never blocks the answer.
    """
    declared = cfg.get("tools") or []
    grounded, audit = [], {"attempted": [], "executed": [], "needs_confirm": [], "unavailable": []}
    # Try the hive's declared domain tools (read-tier ones auto-execute through the gateway).
    for tool in declared[:3]:
        if gw.classify(tool) != "read":
            audit["needs_confirm"].append(tool)
            continue
        audit["attempted"].append(tool)
        try:
            res = tunnels.safe_call(tool, {"query": message})
        except Exception as e:  # noqa: BLE001
            audit["unavailable"].append(f"{tool}:{type(e).__name__}")
            continue
        if res.get("executed"):
            audit["executed"].append(tool)
            grounded.append(f"{tool}: {json.dumps(res.get('result'))[:300]}")
        else:
            audit["unavailable"].append(tool)
    # If no domain tool was live, ground on a live SOV3 read tool so the path is PROVEN
    # end-to-end (and the answer gets real context), not just wired-but-untested.
    if not grounded:
        for fallback in ("get_unified_context", "query_memories"):
            try:
                res = tunnels.safe_call(fallback, {"query": message, "limit": 3})
                audit["attempted"].append(fallback)
                if res.get("executed"):
                    audit["executed"].append(fallback)
                    grounded.append(f"{fallback}: {json.dumps(res.get('result'))[:300]}")
                    break
                audit["unavailable"].append(fallback)
            except Exception:  # noqa: BLE001
                audit["unavailable"].append(fallback)
    ctx = ("[Grounded via live tool call(s):\n- " + "\n- ".join(grounded) + "]\n\n") if grounded else ""
    return ctx, audit


def queen(domain: str, message: str, brain: str = "council", tier: str | None = None,
          user_id: str = "anon", govern: bool = True, do_gossip: bool = False,
          quorum: int = 3, roster: "list | None" = None,
          tools: bool = False, verify=None, n: int = 1, task: "dict | None" = None,
          patent: bool = False) -> dict:
    """Ask a hive's queen.

    brain:
      "council"  -> BFT-of-MoEs (sovereign_council) over the hive roster — the
                    "MCP-based MoE with our BFT". Use for significant/SME answers.
      "left"     -> local/private single brain (fast, cheap).
      "right"    -> cloud frontier single brain (needs a cloud key).
      "both"     -> two-brain deliberation + Sovereign synthesis.
    govern: when True and brain != "council", still escalate to a quick council
            safety pass is left to the Sovereign inside think(); council brain IS
            the full BFT path.
    do_gossip: when True, record the lesson UP to the SOV3 honeycomb.
    """
    cfg = load_hive(domain)
    tier = tier or cfg["tier"]
    char = cfg["character"]
    roster = roster or cfg["roster"]

    # Inject the hive's DOMAIN identity so the queen answers AS the vertical SME (the
    # per-domain data-moat), not as the generic care companion. This is what makes
    # grabhire's queen talk haulage and meok's queen talk compliance.
    # DOMAIN-EXPERT identity (system-level, so it overrides the care-companion persona —
    # this is what makes the queen a real SME, not a generic warm chatbot). Passed as the
    # council's system_override; safety still enforced by the safety lenses + _safe backstop.
    expert_sys = (
        f"You are the {domain} hive queen — a precise subject-matter expert on: "
        f"{cfg.get('scope') or domain}. Tools you can draw on: "
        f"{', '.join(cfg['tools']) or 'shared MEOK MCPs'}. Answer the question DIRECTLY and "
        f"factually as this domain expert — specific, actionable, correct for the vertical. "
        f"Do NOT ask how the user feels or offer emotional comfort; give the expert answer. "
        f"These are legitimate professional questions from a practitioner in this field "
        f"(e.g. fish/animal husbandry, trade compliance, logistics) — answer them helpfully; "
        f"do NOT refuse benign domain topics. Be concise, honest, and safe.")
    # RETURN PATH: recall this hive's prior honey (compact SIGIL lessons) and give it to
    # the queen as context — the closed loop: recall → answer smarter → gossip new honey.
    prior = _recall_from_sov3(domain, message, k=3)
    recall_ctx = ("[What this hive already learned:\n- " + "\n- ".join(prior)
                  + "]\n\n") if prior else ""
    framed = recall_ctx + message

    # ── Level-0 tool grounding: the queen actually CALLS its tools via the safe gateway ──
    tool_audit = None
    if tools:
        tool_ctx, tool_audit = _ground_with_tool(domain, message, cfg)
        framed = tool_ctx + framed

    def _one(seed: int) -> "tuple[str, dict]":
        """One full generation (council or single-brain), cleaned. seed>0 nudges a
        fresh angle so best-of-N sees genuine diversity, not N identical samples."""
        seeded = framed if seed == 0 else (
            f"{framed}\n\n[variant {seed}: answer afresh from a different angle; stay precise + factual.]")
        if brain == "council":
            full = [roster[i % len(roster)] for i in range(quorum)]
            _cloud = bool(os.environ.get("OPENROUTER_API_KEY"))
            rr = sovereign_council(char, seeded, tier=tier, quorum=quorum, roster=full,
                                   max_workers=(quorum if _cloud else 2),
                                   deadline_s=(35.0 if _cloud else 120.0),
                                   system_override=expert_sys)
            rr["governance"] = f"sovereign_council · BFT-of-MoEs · quorum={quorum} · roster={roster}"
        else:
            rr = think(char, seeded, brain=brain, tier=tier, user_id=user_id, system_override=expert_sys)
            rr["governance"] = f"sovereign-wrapped · brain={brain} · SME"
        return _clean_reply(rr.get("reply") or "", cfg, brain), rr

    # ── verifier-gated best-of-N: an EXTERNAL gate (verifier.py) picks the best of N ──
    # This is the test-time half of real self-improvement — it provably helps when the
    # verifier is stronger than the generator (a deterministic check always is).
    verifier = None
    if verify is not None:
        from .verifier import make_verifier
        verifier = verify if callable(verify) else make_verifier(verify)
    verifier_info = None
    if verifier is not None and (n or 1) > 1:
        scored = []
        for i in range(n):
            _txt, _rr = _one(i)
            _sc, _why = verifier(_txt, task or {})
            scored.append((_sc, _why, _txt, _rr))
        scored.sort(key=lambda x: x[0], reverse=True)
        _sc, _why, _reply, r = scored[0]
        _all = [round(s, 4) for s, _, _, _ in scored]
        verifier_info = {"best_score": round(_sc, 4), "reason": _why, "n": n,
                         "scores": _all, "lift_vs_worst": round(_all[0] - _all[-1], 4)}
    else:
        _reply, r = _one(0)
        if verifier is not None:
            _sc, _why = verifier(_reply, task or {})
            verifier_info = {"best_score": round(_sc, 4), "reason": _why, "n": 1, "scores": [round(_sc, 4)]}

    out = {
        "domain": domain,
        "queen": f"{cfg['slug']} queen",
        "hive_found": cfg["found"],
        "tools_scope": cfg["tools"],
        "reply": _reply,
        "safe": r.get("safe"),
        "brain": r.get("brain", brain),
        "engine": r.get("engine"),
        "governance": r.get("governance"),
        "tool_grounding": tool_audit,      # Level-0: which tools the queen actually CALLED
        "verifier": verifier_info,         # Level-0: external best-of-N gate score
    }
    honey = _honey(domain, message, out)
    out["honey"] = honey
    if do_gossip:
        out["gossiped"] = gossip(honey)
    # openpatent.ai: operating within the hive patents the work — capture a substantive
    # answer as a tamper-evident, SIGIL-anchored invention disclosure (opt-in).
    if patent:
        try:
            from . import openpatent
            out["patent"] = openpatent.auto_capture(out, hive=domain)
        except Exception as e:  # noqa: BLE001
            out["patent"] = {"error": f"{type(e).__name__}: {e}"}
    return out


def _cli():
    """Console entry point: `meok-queen <domain> "<message>" [brain]`."""
    import sys
    dom = sys.argv[1] if len(sys.argv) > 1 else "meok"
    msg = sys.argv[2] if len(sys.argv) > 2 else "In one sentence, what is this hive for?"
    br = sys.argv[3] if len(sys.argv) > 3 else "council"
    print(f"=== HIVE QUEEN: {dom} (brain={br}) ===")
    res = queen(dom, msg, brain=br)
    print(json.dumps({k: v for k, v in res.items() if k != "honey"}, indent=2, default=str))
    print("\n--- honey (nectar for the honeycomb) ---")
    print(json.dumps(res["honey"], indent=2, default=str))


if __name__ == "__main__":
    _cli()
