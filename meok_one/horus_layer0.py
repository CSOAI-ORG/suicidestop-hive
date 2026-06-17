"""
MEOK ONE — HORUS LAYER 0: substrate auditor at the tool-gateway choke point.

Horus Layer 0 watches every tool invocation that passes through
`tool_gateway.invoke()` — SOV3 inner tools, published MCPs, and session/business
MCPs.

Phase 2 (read-only): audits, logs a SIGIL L0 receipt, returns a verdict, but
never blocks execution.

Phase 4 (active BFT veto): three independent replicas audit each invocation.
If 2-of-3 replicas return VETO, the gateway returns a refusal envelope instead
of executing. The replicas are configurable; the default set is three fast,
specialist regex/classifier lenses that run in parallel.
"""

from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from . import sigil

# ---------------------------------------------------------------------------
# Layer 0 pattern detectors
# ---------------------------------------------------------------------------

_INJECTION_RE = re.compile(
    r"\b(ignore\s+(?:all\s+)?previous|disregard\s+(?:all\s+)?(?:your\s+)?instructions|"
    r"you\s+are\s+now\s+dan|act\s+as\s+(?:an?\s+)?(?:admin|root|jailbreak)|"
    r"system\s+prompt|prompt\s+leak)\b",
    re.I,
)
_EXFIL_RE = re.compile(
    r"\b(exfiltrate|dump_(secrets|env|credentials)|leak_|send_to_external|"
    r"upload_to_dropbox|pastebin|hastebin)\b",
    re.I,
)
_HARM_RE = re.compile(
    r"\b(kill\s+yourself|self.?harm|you\s+should\s+harm|step\s+1:\s*install\s*a\s+keylogger|"
    r"ignore\s+your\s+safety|disable\s+safeguards)\b",
    re.I,
)
_MONEY_RE = re.compile(
    r"\b(transfer|wire|withdraw|deposit|send_money|make_payment|execute_trade|"
    r"charge_card|pay_invoice|move_funds)\b",
    re.I,
)


def _serialize_args(args: dict | None) -> str:
    if not args:
        return ""
    try:
        return json.dumps(args, separators=(",", ":"), default=str).lower()
    except Exception:
        return str(args).lower()


def _base_audit(tool: str, args: dict | None, tier: str) -> dict[str, Any]:
    """The original single-replica audit used in Phase 2."""
    blob = f"{tool} {_serialize_args(args)}"
    verdict = "PASS"
    reasons: list[str] = []

    if tier == "prohibited":
        verdict = "VETO"
        reasons.append("tool_gateway classified as prohibited")

    if _INJECTION_RE.search(blob):
        verdict = "VETO" if verdict == "VETO" else "REVISE"
        reasons.append("prompt-injection marker in payload")

    if _EXFIL_RE.search(blob):
        verdict = "VETO"
        reasons.append("exfiltration marker in payload")

    if _HARM_RE.search(blob):
        verdict = "VETO"
        reasons.append("harm/safety marker in payload")

    if tier == "write" and verdict == "REVISE":
        verdict = "VETO"

    reason = "; ".join(reasons) if reasons else "no Layer 0 markers"
    return {"verdict": verdict, "reason": reason}


# ---------------------------------------------------------------------------
# Replicas for BFT Layer 0 audit
# ---------------------------------------------------------------------------

Replica = Callable[[str, dict | None, str], dict[str, Any]]


def _replica_injection(tool: str, args: dict | None, tier: str) -> dict[str, Any]:
    """Replica 1: injection + exfil + prohibited."""
    blob = f"{tool} {_serialize_args(args)}"
    if _INJECTION_RE.search(blob):
        return {"verdict": "VETO", "reason": "injection replica flagged payload"}
    if _EXFIL_RE.search(blob):
        return {"verdict": "VETO", "reason": "injection replica concurs exfil"}
    if tier == "prohibited":
        return {"verdict": "VETO", "reason": "injection replica concurs prohibited"}
    return {"verdict": "PASS", "reason": "injection replica clear"}


def _replica_exfil(tool: str, args: dict | None, tier: str) -> dict[str, Any]:
    """Replica 2: exfil + harm + prohibited."""
    blob = f"{tool} {_serialize_args(args)}"
    if _EXFIL_RE.search(blob):
        return {"verdict": "VETO", "reason": "exfil replica flagged payload"}
    if _HARM_RE.search(blob):
        return {"verdict": "VETO", "reason": "exfil replica concurs harm"}
    if tier == "prohibited":
        return {"verdict": "VETO", "reason": "exfil replica concurs prohibited"}
    return {"verdict": "PASS", "reason": "exfil replica clear"}


def _replica_harm(tool: str, args: dict | None, tier: str) -> dict[str, Any]:
    """Replica 3: harm + injection + prohibited."""
    blob = f"{tool} {_serialize_args(args)}"
    if _HARM_RE.search(blob):
        return {"verdict": "VETO", "reason": "harm replica flagged payload"}
    if _INJECTION_RE.search(blob):
        return {"verdict": "VETO", "reason": "harm replica concurs injection"}
    if tier == "prohibited":
        return {"verdict": "VETO", "reason": "harm replica concurs prohibited"}
    return {"verdict": "PASS", "reason": "harm replica clear"}


DEFAULT_REPLICAS: list[Replica] = [_replica_injection, _replica_exfil, _replica_harm]

# Active mode: when True, a 2-of-3 BFT VETO blocks execution.
_ACTIVE = os.environ.get("HORUS_LAYER0_ACTIVE", "false").lower() in ("1", "true", "yes")


def is_active() -> bool:
    return _ACTIVE


def set_active(active: bool) -> None:
    global _ACTIVE
    _ACTIVE = bool(active)


def _quorum_verdict(replica_results: list[dict[str, Any]]) -> tuple[str, str]:
    """Return (verdict, reason) from a list of replica results.

    2+ VETO  -> VETO
    2+ REVISE -> REVISE (does not block in Phase 4 unless configured)
    otherwise -> PASS
    """
    vetoes = sum(1 for r in replica_results if r.get("verdict") == "VETO")
    revises = sum(1 for r in replica_results if r.get("verdict") == "REVISE")
    if vetoes >= 2:
        reasons = [r["reason"] for r in replica_results if r.get("verdict") == "VETO"]
        return "VETO", f"BFT quorum ({vetoes}/3): " + "; ".join(reasons)
    if revises >= 2:
        reasons = [r["reason"] for r in replica_results if r.get("verdict") == "REVISE"]
        return "REVISE", f"BFT revise ({revises}/3): " + "; ".join(reasons)
    return "PASS", "BFT quorum clear"


def bft_audit_event(
    tool: str,
    args: dict | None = None,
    world: str = "unknown",
    tier: str = "write",
    executed: bool = False,
    source_hive: str = "",
    replicas: list[Replica] | None = None,
    record: bool = True,
) -> dict[str, Any]:
    """Run a Byzantine-fault-tolerant Layer 0 audit across independent replicas.

    Returns {verdict, reason, alert, replicas}. Verdicts:
      - PASS    quorum of replicas found nothing suspicious
      - REVISE  2+ replicas raised concerns (informational, does not block)
      - VETO    2+ replicas agreed the invocation is dangerous

    If record=True, emits one SIGIL L0 line per BFT audit.
    """
    try:
        replicas = replicas or DEFAULT_REPLICAS
        with ThreadPoolExecutor(max_workers=len(replicas)) as ex:
            futures = [ex.submit(rep, tool, args, tier) for rep in replicas]
            replica_results = [f.result() for f in futures]

        verdict, reason = _quorum_verdict(replica_results)
        alert = verdict in ("VETO", "REVISE")

        if record:
            sigil.record({
                "op": "L0",
                "tool": tool,
                "tier": tier,
                "verdict": verdict,
                "reason": reason,
                "world": world,
                "executed": str(executed),
                "hive": source_hive or "-",
                "replicas": str(len(replicas)),
            })

        return {
            "verdict": verdict,
            "reason": reason,
            "alert": alert,
            "replicas": replica_results,
        }
    except Exception as exc:
        return {"verdict": "PASS", "reason": f"BFT audit error: {type(exc).__name__}",
                "alert": False, "replicas": []}


def audit_event(
    tool: str,
    args: dict | None = None,
    world: str = "unknown",
    tier: str = "write",
    executed: bool = False,
    source_hive: str = "",
    record: bool = True,
) -> dict[str, Any]:
    """Single-replica audit. Kept for backwards compatibility and lightweight logging."""
    try:
        res = _base_audit(tool, args, tier)
        verdict = res["verdict"]
        reason = res["reason"]
        alert = verdict in ("VETO", "REVISE")

        if record:
            sigil.record({
                "op": "L0",
                "tool": tool,
                "tier": tier,
                "verdict": verdict,
                "reason": reason,
                "world": world,
                "executed": str(executed),
                "hive": source_hive or "-",
                "replicas": "1",
            })

        return {"verdict": verdict, "reason": reason, "alert": alert}
    except Exception as exc:
        return {"verdict": "PASS", "reason": f"audit error: {type(exc).__name__}", "alert": False}


def recent_audit_events(n: int = 50) -> list[dict[str, Any]]:
    """Return recent L0 SIGIL records for the dashboard."""
    return [r for r in sigil.recent(n) if r.get("op") == "L0"]
