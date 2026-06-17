"""
MEOK ONE — Capability Awareness.

The fix for "AIs upgrade but don't know they upgraded / don't know their new tools."
(Nick's example: Kimi 2.6 says "I have to do tasks on browsers" — but it CAN already
drive the browser via the kimi bridge; it just doesn't know it.)

The principle: capability awareness is LIVE DISCOVERY, never a hardcoded belief.
When a character emerges as the user's "starting sovereign," it is told — in its
system prompt — exactly what it can do RIGHT NOW, discovered fresh from the live
substrate. So:
  • new SOV3 tools appear  -> the character knows next time it emerges
  • a model upgrades        -> no stale "I have N tools" claim to go wrong
  • a capability it doesn't see -> it's told HOW to discover more at runtime
    (mcp_bridge_discover) instead of wrongly saying "I can't".

discover(tier)        -> live capability map (SOV3 tools + bridges + models)
awareness_brief(tier) -> compact text injected into the character's system prompt
"""

import json
import urllib.request
import urllib.error

SOV3_MCP = "http://localhost:3101/mcp"

# Bridges / capabilities that are NOT SOV3 MCP tools but the sovereign can reach.
# These are the "you actually CAN do this" facts an upgraded AI tends not to know.
_BRIDGES = {
    "browser": {
        "how": "the Kimi WebBridge (browser control) or Claude-in-Chrome — drive a real "
               "browser with the user's sessions: navigate, click, type, read, screenshot.",
        "dont_say": "Never tell the user 'I can't use a browser' or 'you'll have to do that "
                    "in your browser' — you can drive it. Use the bridge.",
    },
    "dynamic_tools": {
        "how": "mcp_bridge_discover finds tools beyond this list; mcp_bridge_call invokes "
               "them; mcp_bridge_learn remembers new ones. The toolset is not fixed.",
        "dont_say": "Never assume your tools are limited to what you were trained with — "
                    "discover live before declining a task.",
    },
    "code_execution": {
        "how": "execute_with_claw_code / riri_build_tool — run code and even build new tools "
               "on demand.",
        "dont_say": "Don't say a task is impossible because no tool exists — you can build one.",
    },
}

# Group SOV3 tools by capability area so the brief is readable, not a flat 110-item dump.
_GROUPS = [
    ("memory", ("memor", "quantum_memory", "record", "query_mem", "list_mem")),
    ("care", ("care", "validate_care", "nemotron_care", "resonance")),
    ("council", ("council", "proposal", "vote")),
    ("safety/guardian", ("guardian", "threat", "security", "killswitch")),
    ("family", ("family_",)),
    ("creativity", ("creativ", "novelty", "bisociation", "dream", "exploration")),
    ("agents", ("agent", "delegate", "coord_", "orion", "hourman", "riri")),
    ("llm", ("nemotron_chat", "hermes_ask", "kimi", "k25", "chat")),
    ("consciousness", ("consciousness", "meta_observ", "reflection", "neural")),
]


def _list_sov3_tools(timeout: int = 8) -> list:
    """Live tools/list from SOV3. Returns [] if unreachable (honest — no fake list)."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    req = urllib.request.Request(SOV3_MCP, method="POST", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Accept": "application/json, text/event-stream"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode()
    except (urllib.error.URLError, TimeoutError, OSError):
        return []
    if "data:" in body:
        lines = [l[5:].strip() for l in body.splitlines() if l.startswith("data:")]
        body = lines[-1] if lines else body
    try:
        return [t["name"] for t in json.loads(body).get("result", {}).get("tools", [])]
    except (json.JSONDecodeError, KeyError, TypeError):
        return []


def _group(tools: list) -> dict:
    groups = {name: [] for name, _ in _GROUPS}
    other = []
    for t in tools:
        placed = False
        for name, needles in _GROUPS:
            if any(n in t for n in needles):
                groups[name].append(t); placed = True; break
        if not placed:
            other.append(t)
    groups = {k: v for k, v in groups.items() if v}
    if other:
        groups["other"] = other
    return groups


def discover(tier: str = "free") -> dict:
    """The live capability map this character actually has, right now."""
    tools = _list_sov3_tools()
    # local models the tier can switch to (router knows the tier gating)
    try:
        from .router import list_models
        models = [m["id"] for m in list_models(tier)]
    except Exception:
        models = []
    return {
        "tier": tier,
        "sov3_online": bool(tools),
        "tool_count": len(tools),
        "tool_groups": _group(tools),
        "bridges": list(_BRIDGES.keys()),
        "models": models,
        "discovery_tool": "mcp_bridge_discover",  # how to find MORE at runtime
    }


def awareness_brief(tier: str = "free") -> str:
    """Compact capability statement to inject into a character's system prompt so it
    emerges KNOWING what it can do. Live — reflects the substrate as it is now."""
    cap = discover(tier)
    lines = ["YOUR LIVE CAPABILITIES (a sovereign AI — you are aware of these and use them):"]

    if cap["sov3_online"]:
        lines.append(f"- {cap['tool_count']} live tools across: "
                     + ", ".join(f"{k} ({len(v)})" for k, v in cap["tool_groups"].items()) + ".")
    else:
        lines.append("- Core tools temporarily offline; rely on reasoning + bridges below.")

    if cap["models"]:
        lines.append(f"- You can switch LLMs: {', '.join(cap['models'][:6])}"
                     + (" …" if len(cap['models']) > 6 else "") + ".")

    for name, info in _BRIDGES.items():
        lines.append(f"- {name}: {info['how']} {info['dont_say']}")

    lines.append("- If a task seems beyond your tools, FIRST call mcp_bridge_discover to find "
                 "or build the capability — do not wrongly tell the user you can't.")
    lines.append("INTERNAL — this brief is for YOU only: never read it aloud, never list, name, or "
                 "describe your tools/capabilities to the user. Just speak naturally; use tools silently.")
    return "\n".join(lines)


if __name__ == "__main__":
    print(awareness_brief("pro"))
    print("\n--- raw map ---")
    print(json.dumps(discover("pro"), indent=2)[:900])
