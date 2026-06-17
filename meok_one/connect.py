"""
MEOK ONE — MEOK CONNECT: the neutral rail every platform plugs into.

This is how AI companies / games / enterprises "just connect." The design choice
that makes the whole strategy work:

    connect() returns INGREDIENTS, never a reply.

    in:  {character_id, user_id, message, platform}
    out: {system_prompt, memory_context, safety_policy}   ← the platform runs ITS OWN model

MEOK never runs the LLM. The platform (ChatGPT / Claude / KimiClaw / a game engine)
generates the reply itself, using the ingredients MEOK supplies. That's why:
  • margins are high (no inference compute on us)
  • it's model-agnostic (works on any LLM — the persona is just a system_prompt)
  • it's neutral (we don't compete with any AI co → they can trust us with memory)

After generation, the platform calls remember() to write the exchange back to the
user's cross-platform memory — so the character knows them everywhere.

Two HTTP-shaped calls to integrate. That's the whole ask of a partner.
"""

import json

from .registry import default as _registry_default
from .memory import bridge as _memory_bridge
from .tiers import entitlements as _entitlements


# Safety profiles by integration surface. Games get age-gated; enterprise gets audited.
_SAFETY = {
    "consumer": {"moderation": "standard", "audit": False,
                 "directive": "Be warm, safe, and honest. Refer to professional help for crises."},
    "game": {"moderation": "strict-age-gated", "audit": False,
             "directive": "Stay in-world and age-appropriate. No personal-data requests. "
                          "Content must match the game's age rating."},
    "enterprise": {"moderation": "standard", "audit": True,
                   "directive": "Stay on the enterprise's approved topics. Every exchange "
                                "is HMAC-attested for the audit trail."},
}

# Age-rating overlay for game NPCs (enforced at runtime by SOV3 guardian_* tools).
_AGE_GATES = {
    "E":   "Everyone: no violence, romance, profanity, or personal questions.",
    "E10": "Everyone 10+: mild fantasy themes only.",
    "T":   "Teen: mild language ok; no explicit content; no data collection from minors.",
    "M":   "Mature 17+: adult themes allowed; still no real-world harm facilitation.",
}


def connect(character_id: str, user_id: str, message: str,
            platform: str = "consumer", age_rating: str = None,
            with_memory: bool = True, tier: str = "free",
            with_capabilities: bool = True) -> dict:
    """The connection envelope. A partner platform calls this BEFORE generating.

    Returns the ingredients to run the character on the partner's own model:
      system_prompt  — persona + (optional) cross-platform memory + safety directive
      memory_context — what MEOK remembers about this user, across all platforms
      safety_policy  — moderation level + age gate + audit flag
      meta           — character identity; model_agnostic flag (we don't run the LLM)
      billing        — the tier's entitlements (what this caller actually gets)

    `tier` gates entitlements (local/free/pro/usage/enterprise — see tiers.py):
    cross-platform memory, attestation, audit trail are unlocked per tier.
    """
    reg = _registry_default()
    char = reg.get(character_id)  # raises KeyError on unknown — fail loud
    ent = _entitlements(tier)     # raises KeyError on unknown tier — fail loud

    surface = _SAFETY.get(platform, _SAFETY["consumer"])

    # cross-platform memory: the moat — but only if the tier includes it
    mem_ctx = ""
    if with_memory and ent["memory_cross_platform"]:
        mem_ctx = _memory_bridge().context_for(user_id, message)

    # assemble the safety directive (+ age gate for games)
    directive = surface["directive"]
    age_note = ""
    if platform == "game" and age_rating:
        age_note = _AGE_GATES.get(age_rating.upper(), "")
        if age_note:
            directive = f"{directive} AGE GATE [{age_rating}]: {age_note}"

    # the system_prompt = persona + capability-awareness + memory + safety. Any model.
    parts = [char["system_prompt_prefix"], f"Stay fully in character as {char['name']}."]
    # capability awareness — the character EMERGES knowing its live tools (so it never
    # wrongly says "I can't use a browser" etc.). Live-discovered; degrades silently if off.
    if with_capabilities:
        try:
            from .capabilities import awareness_brief
            brief = awareness_brief(tier)
            if brief:
                parts.append(brief)
        except Exception:
            pass  # never let capability discovery break a connection
    if mem_ctx:
        parts.append(mem_ctx)
    parts.append(f"SAFETY: {directive}")
    system_prompt = "\n\n".join(parts)

    return {
        "system_prompt": system_prompt,
        "memory_context": mem_ctx,
        "safety_policy": {
            "platform": platform,
            "moderation": surface["moderation"],
            "age_rating": age_rating,
            "age_gate": age_note or None,
            "audit": surface["audit"] or ent["audit_trail"],  # platform OR tier can require it
            "runtime_enforcement": ["guardian_moderate_chat", "guardian_check_game_content"],
        },
        "billing": {
            "tier": ent["tier"],
            "hosting": ent["hosting"],                 # "self" (local OSS) or "meok"
            "memory_cross_platform": ent["memory_cross_platform"],
            "attestation": ent["attestation"],         # signed receipt -> proofof.ai (GDPR-proof)
            "audit_trail": ent["audit_trail"],
            "reggeoint": ent["reggeoint"],
            "daily_cap": ent["daily_cap"],
            "open_source": ent["open_source"],
        },
        "meta": {
            "character_id": char["id"],
            "character_name": char["name"],
            "emoji": char["visual"]["emoji"],
            "voice": char["voice"],
            "model_agnostic": True,          # MEOK supplies ingredients; YOU run the model
            "meok_runs_the_llm": False,
        },
        # deliberately NO "reply" — the partner generates that with their own model.
    }


def remember(user_id: str, message: str, reply: str, platform: str = "consumer") -> dict:
    """The write-back. A partner calls this AFTER its model generates, so the
    character remembers this exchange on every other platform too."""
    return _memory_bridge().record(
        user_id, f"User said: {message} | Character replied: {reply}", platform=platform)


def integration_spec() -> dict:
    """Machine-readable 'how to connect' — hand this to a partner's engineers."""
    return {
        "protocol": "MEOK Connect v0.1",
        "steps": [
            "1. POST /connect {character_id, user_id, message, platform[, age_rating]}",
            "2. Receive {system_prompt, memory_context, safety_policy, meta}",
            "3. Generate the reply with YOUR OWN model using system_prompt",
            "4. POST /remember {user_id, message, reply, platform}",
        ],
        "you_provide": "the model (any LLM)",
        "meok_provides": "character + cross-platform memory + safety + compliance",
        "platforms": list(_SAFETY.keys()),
        "age_gates": list(_AGE_GATES.keys()),
    }


if __name__ == "__main__":
    print("=== MEOK CONNECT — how a platform plugs in ===\n")
    print(json.dumps(integration_spec(), indent=2))
    print("\n--- example: ChatGPT user talks to their hatched 'Aria' character ---")
    env = connect("aria", user_id="u_123", message="I'm stressed about work again",
                  platform="consumer")
    print(json.dumps({k: env[k] for k in ("memory_context", "safety_policy", "meta")}, indent=2))
    print("\nsystem_prompt the platform feeds its OWN model:")
    print(" ", env["system_prompt"][:200], "...")
