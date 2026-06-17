"""
MEOK ONE — A2A AGENT CARDS: make every hive discoverable by any agent on Earth.

The distribution layer (2026-06-16). Each hive gets an A2A-standard agent card
(`/.well-known/agent.json`) so any A2A-compatible agent can discover its capabilities
and call it. 30 hives → 30 cards + one directory = the "Agent Card Network" play.

Reads each hive's stack.yml (domain, scope, tools) and emits a spec-shaped card.

    generate(hive_root, out_dir) -> {cards, directory_path}
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

_PROTO = "0.3.0"
_ORG = {"organization": "MEOK AI Labs (CSOAI Ltd, UK)", "url": "https://meok.ai"}


def _parse(stack_text: str) -> dict:
    cfg = {"domain": "", "scope": "", "tools": [], "tier": "", "character": ""}
    in_tools = False
    for line in stack_text.splitlines():
        s = line.strip()
        if s.startswith("domain:"):
            cfg["domain"] = s.split(":", 1)[1].strip()
        if s.startswith("tools:"):
            in_tools = True; continue
        if in_tools:
            if s.startswith("- "):
                cfg["tools"].append(s[2:].strip())
            elif s and not s.startswith("#") and not line.startswith(" " * 6):
                in_tools = False
        if s.startswith("scope:") and not cfg["scope"]:
            cfg["scope"] = s.split(":", 1)[1].strip().strip('"')
        if s.startswith("tier:") and not cfg["tier"]:
            cfg["tier"] = s.split(":", 1)[1].strip()
        if s.startswith("character:") and not cfg["character"]:
            cfg["character"] = s.split(":", 1)[1].strip()
    return cfg


def _card(cfg: dict) -> dict:
    domain = cfg["domain"] or "meok.ai"
    base = f"https://{domain}"
    skills = []
    for t in (cfg["tools"] or ["verified-compliance"]):
        skills.append({
            "id": t, "name": t.replace("-", " ").title(),
            "description": f"{t} capability of the {domain} hive (MEOK ONE engine).",
            "tags": ["mcp", "meok", domain.split(".")[0]],
        })
    # every hive also exposes the shared verified-compliance + attestation skills
    skills.append({"id": "verified-compliance", "name": "Verified Compliance",
                   "description": "Regulation-grounded, externally-verified, attested answers "
                                  "(EU AI Act / DORA / NIS2).", "tags": ["compliance", "verified"]})
    return {
        "protocolVersion": _PROTO,
        "name": f"{domain} hive",
        "description": (cfg["scope"] or f"The {domain} domain hive — a verified, "
                        "BFT-governed MEOK agent.")[:280],
        "url": base, "preferredTransport": "JSONRPC",
        "provider": _ORG, "version": "1.0.0",
        "documentationUrl": "https://meok.ai/docs",
        "capabilities": {"streaming": True, "pushNotifications": False,
                         "stateTransitionHistory": True},
        "defaultInputModes": ["text/plain", "application/json"],
        "defaultOutputModes": ["text/plain", "application/json"],
        "skills": skills,
        "securitySchemes": {"apiKey": {"type": "apiKey", "in": "header", "name": "X-API-Key"}},
        "x_meok": {"tier": cfg["tier"], "engine": "meok-one", "governance": "BFT 12-lens council",
                   "attestation": "proofof.ai", "ip": "openpatent.ai"},
    }


def generate(hive_root: str, out_dir: str) -> dict:
    root = Path(hive_root).expanduser()
    out = Path(out_dir).expanduser(); out.mkdir(parents=True, exist_ok=True)
    cards, directory = [], []
    for stack in sorted(root.glob("*-hive/stack.yml")):
        cfg = _parse(stack.read_text())
        if not cfg["domain"]:
            cfg["domain"] = stack.parent.name.replace("-hive", "") + ".ai"
        card = _card(cfg)
        slug = re.sub(r"[^a-z0-9]+", "-", cfg["domain"].lower()).strip("-")
        (out / f"{slug}.agent.json").write_text(json.dumps(card, indent=2))
        cards.append(slug)
        directory.append({"name": card["name"], "url": card["url"],
                          "card": f"{card['url']}/.well-known/agent.json",
                          "skills": [s["id"] for s in card["skills"]], "tier": cfg["tier"]})
    (out / "directory.json").write_text(json.dumps({
        "name": "MEOK Agent Network", "provider": _ORG,
        "count": len(directory), "agents": directory}, indent=2))
    return {"cards": len(cards), "out_dir": str(out), "directory": str(out / "directory.json")}


if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else str(Path.home() / "hive-staging")
    out = sys.argv[2] if len(sys.argv) > 2 else str(Path.home() / "agent-cards")
    print(json.dumps(generate(root, out), indent=2))
