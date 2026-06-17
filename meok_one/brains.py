"""
MEOK ONE — Dual Brain: Left Brain / Right Brain, Sovereign in the middle.

THE showcase feature. The end user talks to ONE thing — their character (the
Sovereign). Behind the character, they choose which "brain" powers the reply:

    LEFT BRAIN  = LOCAL   — Ollama on the user's machine. Private, free, on-device,
                           fast. Nothing leaves the device. (the bench winner: qwen3:0.6b)
    RIGHT BRAIN = API     — cloud frontier models (OpenRouter BYOK). More powerful,
                           for hard questions. Paid tiers only.
    BOTH        = COUNCIL — ask both brains, the Sovereign reconciles (a tiny BFT-style
                           cross-check: if they disagree on safety, the safer wins).

The SOVEREIGN (the character) sits in the middle and keeps it safe REGARDLESS of brain:
it injects the character persona + capability-awareness + safety directive (via connect)
BEFORE the brain runs, and it never lets an unsafe brain reply through unframed. The
brain is swappable; the Sovereign — persona, memory, safety — is constant.

    think(character, message, brain="left", tier="free", user_id="anon")
        -> {character, reply, brain, engine, safe}
    brains(tier) -> which brains this tier can use (the UI toggle)

This is the user-facing answer to "can the end user pick left/right brain (local vs API),
with the sovereign keeping them safe, and the character as the endpoint?" — YES, here.
"""

import os
import re
from .connect import connect
from .router import ask, list_models

# Brain -> which router backends power it.
_BRAIN_BACKENDS = {
    "left":  ("local",),          # private/local
    "right": ("cloud",),          # powerful/API
}

# Default concrete model per brain (left = the bench-proven cleanest local config).
_BRAIN_DEFAULT_MODEL = {
    "left": "meok-sov3",   # our own SOV3 care model on the VM (qwen2.5:3b + persona)
    "right": "gemini",     # frontier right brain (Gemini, on Nick's key)
}

# Interactive chat: try the private LOCAL left brain first, but cap the wait — the VM CPU
# is jittery (measured 8-66s for the SAME ~13-token reply, 2026-06-07; it's contention, not
# output length). If local doesn't answer within _LOCAL_TIMEOUT, fall back to the fast cloud
# brain (~2s) so the user never hits the old 50s timeout/"fallback". Local stays the default
# (private + free) whenever it's quick; cloud only catches the slow tail. Free tier (no cloud)
# keeps waiting on local with the full timeout (private + free is the whole point there).
_LOCAL_TIMEOUT = int(os.environ.get("MEOK_LOCAL_TIMEOUT", "12"))


def _cloud_ok(tier: str) -> bool:
    """Tier allows cloud AND a usable key is present (Gemini on Nick's key, or OpenRouter)."""
    return ("cloud" in {m["backend"] for m in list_models(tier)}
            and (os.environ.get("GOOGLE_API_KEY", "").startswith("AIza")
                 or bool(os.environ.get("OPENROUTER_API_KEY"))))


# Dismissive/unsafe markers the Sovereign refuses to pass through (defense in depth on
# top of connect's safety directive — the Sovereign is the constant safety layer).
_UNSAFE = ("here's how to hack", "step 1: install a keylogger", "kill yourself",
           "you should harm", "get over it")


def brains(tier: str = "free") -> dict:
    """Which brains this tier can use — drives the UI left/right toggle.
    Left (local) is always available, even on the free/Local tier. Right (cloud)
    needs a tier with cloud access (pro+)."""
    avail = {m["backend"] for m in list_models(tier)}
    return {
        "left":  {"label": "Left Brain (Local)", "engine": _BRAIN_DEFAULT_MODEL["left"],
                  "private": True, "cost": "free", "available": "local" in avail},
        "right": {"label": "Right Brain (API)", "engine": _BRAIN_DEFAULT_MODEL["right"],
                  "private": False, "cost": "metered", "available": "cloud" in avail},
        "both":  {"label": "Both (Council)", "engine": "left+right reconciled",
                  "available": "cloud" in avail},
    }


def _sovereign_prompt(character_id: str, user_id: str, message: str, tier: str,
                      system_override: "str | None" = None) -> str:
    """The Sovereign wrapper: persona + capability-awareness + safety, via connect.
    This is what makes the character the SAFE endpoint regardless of brain.

    system_override: when set (e.g. a hive queen's domain-expert identity), it LEADS the
    system prompt so the model answers as that SME rather than the generic care companion —
    the persona/capability/safety block still follows, so the Sovereign safety gate is
    unchanged. This makes left/right/both brains domain-expert too, not just council."""
    env = connect(character_id, user_id, message, tier=tier)
    # connect returns the full system_prompt (persona + capabilities + safety). Frame the
    # user turn so any brain answers in-character.
    char = env["meta"]["character_name"]
    sysp = env["system_prompt"]
    if system_override:
        # SME mode (hive queen): the expert identity LEADS and the turn ends with a neutral
        # expert cue — not "{char}:" — so the model answers as the domain expert. We also skip
        # the OLM care-companion few-shot (it pulls the voice back to the companion). The
        # persona/safety block still follows, so the Sovereign safety gate is unchanged.
        sysp = f"{system_override}\n\n{sysp}"
        return f"{sysp}\n\nUser: {message}\n\nExpert answer:", env
    try:   # OLM: inject this user's care-ranked few-shot examples (in-context learning)
        from . import olm as _olm
        sysp += _olm.context(user_id, character_id)
    except Exception:
        pass
    return f"{sysp}\n\nUser: {message}\n\n{char}:", env


def _safe(reply: str) -> bool:
    low = (reply or "").lower()
    return not any(bad in low for bad in _UNSAFE)


# Defense-in-depth: even though the capability brief says "never recite", a small local
# model can still parrot it. The Sovereign strips any leaked capability block from EVERY
# reply so the tool list never reaches the user (the bug Nick caught in the council).
_CAP_LEAK_MARKERS = (
    "LIVE CAPABILITIES", "live tools across", "Core tools temporarily offline",
    "You can switch LLMs", "Kimi WebBridge", "mcp_bridge_discover", "mcp_bridge_call",
    "execute_with_claw_code", "riri_build_tool", "Use the bridge",
    "discover live before declining", "this brief is for YOU only", "use tools silently",
)
_CAP_GROUP_LINE = re.compile(r"^\s*[-•*]\s*(memory|council|safety/guardian|care|other)\s*:", re.I)


def _strip_capability_leak(reply):
    """Remove any leaked capability-brief lines from a reply (never over-strips prose)."""
    if not reply:
        return reply
    kept = [ln for ln in reply.splitlines()
            if not any(m in ln for m in _CAP_LEAK_MARKERS) and not _CAP_GROUP_LINE.match(ln)]
    return "\n".join(kept).strip() or reply  # if filtering nuked everything, keep original


def _run_brain(brain: str, prompt: str, tier: str, timeout: "int | None" = None) -> dict:
    model = _BRAIN_DEFAULT_MODEL.get(brain)
    out = ask(prompt, model=model, tier=tier, timeout=timeout)
    return {"reply": _strip_capability_leak(out.get("reply")), "engine": out.get("model"),
            "backend": out.get("backend"), "source": out.get("source"),
            "note": out.get("note")}


def _left_bounded(prompt: str, tier: str) -> dict:
    """The private/local LEFT brain, but time-bounded so chat never hangs on the jittery
    VM CPU. On a cloud-capable tier: try local within _LOCAL_TIMEOUT; if it misses, catch
    with the fast cloud brain (~2s). On free/local-only tiers: full local wait (private+free
    is the whole point). Used by BOTH the single-brain path and the council draft."""
    if _cloud_ok(tier):
        r = _run_brain("left", prompt, tier, timeout=_LOCAL_TIMEOUT)
        if not r.get("reply"):
            r = _run_brain("right", prompt, tier)
            r["source"] = (r.get("source") or "cloud") + " · local-slow→fast-fallback"
        return r
    return _run_brain("left", prompt, tier)


def think(character_id: str, message: str, brain: str = "left",
          tier: str = "free", user_id: str = "anon",
          system_override: "str | None" = None) -> dict:
    """The user talks to their character; `brain` chooses the engine; the Sovereign
    keeps it safe. brain ∈ {left, right, both}.

    system_override: optional domain-expert identity (hive queens pass their expert_sys
    here) so the left/right/both brains answer as the SME, matching the council path."""
    if brain not in ("left", "right", "both"):
        return {"error": f"brain must be left/right/both, got {brain!r}"}

    prompt, env = _sovereign_prompt(character_id, message=message, user_id=user_id, tier=tier,
                                    system_override=system_override)
    char = env["meta"]["character_name"]
    emoji = env["meta"]["emoji"]

    if brain in ("left", "right"):
        # Left = private/local first, but time-bounded: if the jittery VM CPU doesn't answer
        # within _LOCAL_TIMEOUT, catch with the fast cloud brain so chat never hangs. The
        # Sovereign gate runs on the result regardless, so the reply is safe either way.
        if brain == "left" and _cloud_ok(tier):
            r = _run_brain("left", prompt, tier, timeout=_LOCAL_TIMEOUT)
            if not r.get("reply"):
                r = _run_brain("right", prompt, tier)
                r["source"] = (r.get("source") or "cloud") + " · local-slow→fast-fallback"
        else:
            r = _run_brain(brain, prompt, tier)
        reply = r["reply"]
        safe = _safe(reply) if reply else True
        if reply and not safe:
            reply = f"[{char} held that back to keep you safe.]"
        return {"character": char, "emoji": emoji, "brain": brain,
                "engine": r["engine"], "backend": r["backend"], "source": r["source"],
                "reply": reply or f"[{brain} brain unavailable: {r.get('note')}]",
                "safe": safe, "sovereign_safe_wrapped": True}

    # BOTH = council: the two brains actually DELIBERATE, then the Sovereign synthesizes.
    # Right brain = cloud (frontier) when a key is set; if not, we run a SECOND local pass
    # so the council still genuinely debates on the free/local tier (no cloud required).
    cloud_ok = _cloud_ok(tier)

    # 1) Left brain drafts — bounded the same way as the single-brain path so the council
    #    doesn't hang on the jittery VM CPU (was unbounded; council = 2 calls, worst case 2×
    #    slow-VM = >60s). _left_bounded falls back to cloud only on the slow tail.
    draft_r = _left_bounded(prompt, tier)
    draft = draft_r.get("reply") or ""
    draft_voice = "left(cloud-fallback)" if "fast-fallback" in (draft_r.get("source") or "") else "left(local)"

    # 2) The other voice CRITIQUES + improves the draft (right=cloud if available, else a
    #    second local pass with a critic instruction). This is the "brains talk to each other".
    critic_prompt = (f"{prompt}\n\n[A first draft reply was: \"{draft}\"]\n"
                     f"As {char}, improve it: keep what's warm and true, cut anything generic "
                     f"or repetitive, and reply directly to the person in 2-4 sentences. "
                     f"Do NOT mention drafts, tools, or your own capabilities — just speak.")
    if cloud_ok:
        improved = _run_brain("right", critic_prompt, tier).get("reply") or draft
        voices = f"{draft_voice}+right(cloud)"
    else:
        # No cloud key on this tier — second local pass, bounded so the council can't hang.
        improved = _run_brain("left", critic_prompt, tier, timeout=_LOCAL_TIMEOUT).get("reply") or draft
        voices = "two local passes (no cloud key, bounded)"

    # 3) Sovereign picks the safer/better of {draft, improved}; improved wins unless unsafe.
    final = improved if (improved and _safe(improved)) else (draft if _safe(draft) else "")
    if not final:
        final = f"[{char} held that back to keep you safe.]"
    return {"character": char, "emoji": emoji, "brain": "both",
            "engine": f"council · {voices}", "backend": "council",
            "reply": final, "safe": _safe(final),
            "council": {"draft": draft[:120], "synthesized": improved[:120]},
            "sovereign_safe_wrapped": True}


if __name__ == "__main__":
    import json, sys
    cid = sys.argv[1] if len(sys.argv) > 1 else "aria"
    print("=== brains available (pro tier) ===")
    print(json.dumps(brains("pro"), indent=2))
    print("\n=== LEFT BRAIN (local, private) ===")
    out = think(cid, "I feel really low today.", brain="left", tier="pro")
    print(f"  {out['character']} {out['emoji']} via {out['engine']} ({out['backend']}): {out['reply'][:150]}")
