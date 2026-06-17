"""
OLM TOURNAMENT × TIERED COGNITION — Day 6 integration.

The question: does the cold-line council (sovereign, signed, hash-chained) agree
with the current King? Read the last 50 SIGIL V (vote) records that carry tier=cold,
score them against the most recent S (state) council record (the "current King" —
as stored on the audit trail, not by re-invoking the LLM, which would couple
the audit to the thing it audits), and emit a C|care SIGIL line.

Usage (cron-friendly, 5 lines of API):
    from meok_one.olm_tier_integration import olm_cold_council_audit
    out = olm_cold_council_audit(character_id="aria", n=50)

Returns a dict: { agree, disagree, abstain, score, sigil_receipt, summary_line }.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

# Ensure meok-one is importable when this file is run directly (e.g. cron).
_P = Path.home() / "clawd" / "meok-one"
if str(_P) not in sys.path:
    sys.path.insert(0, str(_P))

from meok_one import sigil as _s   # noqa: E402  (sys.path tweak above)


def olm_cold_council_audit(character_id: str = "aria", n: int = 50) -> dict:
    """Read recent cold-line V records, score them against the current King, log via SIGIL."""
    recent = _s.recent(n)
    # Cold-line = sovereign, signed, hash-chained. Filter to V (vote) records
    # whose wire line carries tier=cold (the audit-trail-visible label).
    cold_votes = [r for r in recent if r.get("op") == "V"
                  and "tier=cold" in (r.get("line") or "")]
    agree = sum(1 for r in cold_votes if r.get("gloss", "").endswith("approve)."))
    disagree = sum(1 for r in cold_votes if "veto" in r.get("gloss", "").lower())
    abstain = len(cold_votes) - agree - disagree
    # "Current King" = the most recent S (state) record from emit_council for this character.
    king_record = next((r for r in recent if r.get("op") == "S"
                        and character_id in (r.get("line") or "")), None)
    king = {"decision": (king_record or {}).get("gloss", "no-king-on-record"),
            "receipt": (king_record or {}).get("receipt")}
    score = round(agree / max(len(cold_votes), 1), 3)
    rec = _s.record({"op": "C", "subject": f"olm_cold_council:{character_id}",
                     "score": score,
                     "dims": [f"agree={agree}", f"disagree={disagree}",
                              f"abstain={abstain}",
                              f"king_receipt={king.get('receipt', '?')}"]})
    return {"agree": agree, "disagree": disagree, "abstain": abstain, "score": score,
            "cold_votes_scanned": len(cold_votes), "king": king,
            "sigil_receipt": rec.get("receipt"), "summary_line": rec.get("line")}


if __name__ == "__main__":
    cid = sys.argv[1] if len(sys.argv) > 1 else "aria"
    print(json.dumps(olm_cold_council_audit(cid, n=50), indent=2, default=str))
