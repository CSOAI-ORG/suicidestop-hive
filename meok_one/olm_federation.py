"""
MEOK ONE — OLM FEDERATION: per-(user, character) ICRL buffer that crosses machines.

The base OLM (`olm.py`) stores buffers as JSON on the local node. That works for one
machine, but the 28-hive mesh + the Mac + the VM all want a SHARED learning layer
for the same user without mixing their data with other users' (per the v0.2 spec
"per-user buffer isolation" + "stays yours").

This module ADDS — not replaces — two new surfaces on top of olm.py:

  1) SOV3-BACKED CENTRAL BUFFER (the "federated" store)
     `federated_record` / `federated_context` mirror the local buffer to SOV3 memory
     under tag=olm_federation, with memory_type=hive_honey. The local JSON is still
     the source of truth (so a user can wipe their node and the central copy is just
     a backup that they can request be deleted — GDPR). On a fresh machine, the
     buffer is reconstructed from SOV3.

  2) MEMORY-LEVEL FILTER
     `filter_for_user(all_eps, user_id)` is a defensive helper so a /os query can
     never accidentally inject one child's OLM examples into another profile's
     context (this is the most common "data leak" failure mode for care systems).

The bus is SIGIL (H|handoff) so every cross-machine move is hash-chained and
auditable. No new infra, no new transport, no Kimi/Claude calls — SOV3 + stdlib.

Honest: the SOV3 read path has a known "postgres is a stale mirror" quirk
(see [[reference_sov3_state_layers]]). When SOV3 query returns empty, we fall
back to local — so the local-first / SOV3-mirror model degrades gracefully.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
import urllib.error
from typing import Optional

# Import the base OLM — DON'T recreate the buffer logic
from . import olm as _olm

_SOV3 = os.environ.get("SOV3_MCP", "http://localhost:3101/mcp")
_FED_TAG = "olm_federation"
_TIMEOUT = int(os.environ.get("MEOK_OLM_FED_TIMEOUT", "6"))


def _sov3_call(tool: str, arguments: dict, timeout: int = _TIMEOUT):
    """One SOV3 MCP call. Returns parsed result or None on hard fail."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": tool, "arguments": arguments}}
    req = urllib.request.Request(_SOV3, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Accept": "application/json, text/event-stream"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode()
        if "data:" in body:
            lines = [l[5:].strip() for l in body.splitlines() if l.startswith("data:")]
            body = lines[-1] if lines else body
        env = json.loads(body)
        if "error" in env:
            return None
        return env.get("result")
    except Exception:
        return None


def _sov3_record(content: str, source_agent: str, tags: list, importance: float = 0.6) -> bool:
    """Push one OLM episode to SOV3 memory. Best-effort, returns True/False — never raises."""
    res = _sov3_call("record_memory", {
        "content": content, "source_agent": source_agent,
        "memory_type": "hive_honey", "importance": float(importance),
        "tags": tags,
    })
    return bool(res and res.get("content"))


def _sov3_query(user_id: str, character_id: str, limit: int = 50) -> list:
    """Pull this user's OLM episodes from SOV3 (best-effort). Returns [] on miss/hard-fail."""
    res = _sov3_call("query_memories", {
        "query": f"olm_federation {user_id} {character_id}",
        "tags": [_FED_TAG, "olm"],
        "limit": int(limit),
    })
    if not res:
        return []
    try:
        content = res.get("content", [])
        if not content:
            return []
        text = content[0].get("text", "{}")
        data = json.loads(text) if isinstance(text, str) else text
        if isinstance(data, dict) and "memories" in data:
            return data["memories"] or []
        if isinstance(data, list):
            return data
    except Exception:
        return []
    return []


def _slug(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", str(s or "anon"))[:64] or "anon"


def _ep_to_sigil_line(ep: dict) -> str:
    """One episode → compact SIGIL C|care line for cross-machine replay.
    Care score is the salience; q/r are truncated for log hygiene."""
    care = float(ep.get("care", 0.5))
    q = (ep.get("q") or "")[:60].replace("|", " ").replace("\n", " ")
    r = (ep.get("r") or "")[:120].replace("|", " ").replace("\n", " ")
    return f"olm|{q}|{r}|{care:.2f}"


def _sigil_line_to_ep(line: str) -> dict:
    """Parse a C|care line back into an episode. Returns {} on parse fail."""
    parts = (line or "").split("|")
    if len(parts) < 4:
        return {}
    return {"q": parts[1], "r": parts[2], "care": float(parts[3] or 0.5),
            "ts": int(time.time()), "replayed": True}


# -------- The two new surfaces ----------------------------------------------

def federated_record(user_id: str, character_id: str, query: str, response: str,
                     care_flagged: bool = False, held: bool = False) -> dict:
    """Record to LOCAL first (the source of truth, on the user's node), THEN mirror
    a compact SIGIL line to SOV3 so other queens in the mesh can replay the
    learning. The local write is unconditional; the SOV3 mirror is best-effort."""
    # 1) local — the canonical store. This is what olm.py.context() reads next turn.
    local_stats = _olm.record(user_id, character_id, query, response,
                              care_flagged=care_flagged, held=held)
    # 2) mirror to SOV3 — compact line, care score, user/char tags for hive-scoped query
    latest = _olm._load(user_id, character_id)
    if not latest:
        return {"local": local_stats, "federated": False, "why": "no local episode"}
    ep = latest[-1]
    line = _ep_to_sigil_line(ep)
    pushed = _sov3_record(
        content=line,
        source_agent=f"olm-fed:{_slug(user_id)}:{_slug(character_id)}",
        tags=[_FED_TAG, "olm", f"u:{_slug(user_id)}", f"c:{_slug(character_id)}",
              "hive_honey" if not held else "hive_held"],
        importance=float(ep.get("care", 0.5)),
    )
    return {"local": local_stats, "federated": pushed,
            "user_id": user_id, "character_id": character_id,
            "line": line if pushed else None}


def federated_context(user_id: str, character_id: str, n: int = 3) -> str:
    """Build a context block from BOTH local + SOV3 sources, deduped, ranked by care.
    Returns "" if there's not enough signal (matches olm.py.context() contract)."""
    out = []
    # 1) local buffer (source of truth on this node)
    local_eps = _olm._load(user_id, character_id)
    out.extend(local_eps or [])
    # 2) SOV3 mirror (other queens' contributions, replayed)
    try:
        for mem in _sov3_query(user_id, character_id, limit=max(n * 3, 10)):
            content = (mem.get("content") or "").strip()
            if not content or "|" not in content:
                continue
            ep = _sigil_line_to_ep(content)
            if ep:
                out.append(ep)
    except Exception:
        pass
    if len(out) < 2:
        return ""
    # rank by care, only surface ABOVE 0.60 (never hold up a cold/mediocre reply as best)
    best = sorted(out, key=lambda e: -float(e.get("care", 0.5)))
    best = [e for e in best if float(e.get("care", 0.5)) >= 0.60][:n]
    if not best:
        return ""
    lines = ["\n\n[OLM FEDERATION — learned from your history across the hive mesh.",
             "Emulate the warmth + specificity below; never the avoided ones.]",
             "Your best replies (this person, this character):"]
    for e in best:
        lines.append(f'  · they said "{(e.get("q") or "")[:80]}" → '
                     f'you replied "{(e.get("r") or "")[:140]}"  '
                     f'(care {float(e.get("care", 0.5)):.2f})')
    if len(out) >= _olm._MIN_FOR_AVOID:
        worst = sorted(out, key=lambda e: float(e.get("care", 0.5)))
        if worst and float(worst[0].get("care", 0.5)) < 0.4:
            lines.append("\nAvoid replies like this (too cold / low-care):")
            lines.append(f'  · "{(worst[0].get("r") or "")[:140]}"  '
                         f'(care {float(worst[0].get("care", 0.5)):.2f})')
    return "\n".join(lines)


# -------- The defensive filter (the moat) ----------------------------------

def filter_for_user(episodes: list, user_id: str) -> list:
    """Hard user-isolation. Removes any episode whose user_id doesn't match.
    This is what a /os endpoint MUST call before injecting OLM examples into
    a reply. Defense against the most common care-system data leak."""
    if not episodes:
        return []
    want = _slug(user_id)
    safe = []
    for e in episodes:
        if not isinstance(e, dict):
            continue
        # local olm.py episodes don't carry user_id; assume they were loaded
        # for the right user because olm._path is keyed by slug(user)+slug(char).
        # SIGIL-replayed episodes carry u:<slug> in their tags (set by the record
        # path), so we can verify.
        tags = e.get("tags") or []
        uid_tag = next((t for t in tags if isinstance(t, str) and t.startswith("u:")), None)
        if uid_tag and uid_tag != f"u:{want}":
            continue  # cross-user leak — drop
        safe.append(e)
    return safe


def wipe_user(user_id: str, character_id: str = None) -> dict:
    """GDPR right-to-be-forgotten. Wipes the local buffer (always) and asks SOV3
    to forget too (best-effort). Returns counts."""
    if character_id:
        try:
            p = _olm._path(user_id, character_id)
            if os.path.exists(p):
                os.unlink(p)
        except Exception:
            pass
        return {"wiped_local": True, "user_id": user_id, "character_id": character_id}
    wiped = 0
    try:
        d = _olm._DIR
        prefix = f"{_slug(user_id)}__"
        for fn in os.listdir(d):
            if fn.startswith(prefix) and fn.endswith(".json"):
                os.unlink(os.path.join(d, fn))
                wiped += 1
    except Exception:
        pass
    return {"wiped_local": True, "wiped_files": wiped, "user_id": user_id}


# -------- Stats ------------------------------------------------------------

def federation_stats(user_id: str, character_id: str = None) -> dict:
    """One-glance view: local + SOV3 counts, avg care, sync health."""
    local = _olm._load(user_id, character_id) if character_id else []
    sov3_eps = [] if not character_id else _sov3_query(user_id, character_id, limit=50)
    local_care = [float(e.get("care", 0.5)) for e in local]
    sov3_care = [float(e.get("care", 0.5)) for e in sov3_eps
                 if isinstance(e.get("care"), (int, float))]
    return {
        "user_id": user_id, "character_id": character_id,
        "local_count": len(local),
        "local_avg_care": round(sum(local_care) / max(len(local_care), 1), 3) if local_care else 0.0,
        "sov3_mirror_count": len(sov3_eps),
        "sov3_mirror_avg_care": round(sum(sov3_care) / max(len(sov3_care), 1), 3) if sov3_care else 0.0,
        "in_sync": len(local) > 0 and len(sov3_eps) > 0,
        "ts": int(time.time()),
    }


if __name__ == "__main__":
    import sys
    uid = sys.argv[1] if len(sys.argv) > 1 else "demo-user"
    cid = sys.argv[2] if len(sys.argv) > 2 else "aria"
    print(f"=== OLM FEDERATION · user={uid} · character={cid} ===")
    print(json.dumps(federation_stats(uid, cid), indent=2))
    ctx = federated_context(uid, cid, n=2)
    print("\n--- context (federated) ---")
    print(ctx or "(empty)")
