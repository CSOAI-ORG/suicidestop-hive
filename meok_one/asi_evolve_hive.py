"""
MEOK ONE — ASI-EVOLVE HIVE: self-improving harness evolution under governance.

ASI-Evolve consumes the cross-hive telemetry stream, proposes harness-genome
candidates, scores them in a local sandbox, and submits retainable variants to
the BFT Council gate. Every proposal and retention vote is SIGIL-recorded.

This is the sovereign wrapper around autonomous evolution — the dragon grows
scales, but only the Council decides which scales it keeps.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from . import sigil
from . import telemetry


@dataclass
class HarnessCandidate:
    """One evolvable harness genome candidate."""

    id: str
    target_capability: str
    mutation: str
    parent: str | None = None
    score: float | None = None
    retained: bool | None = None
    proposed_at: float = field(default_factory=time.time)
    council_receipt: str | None = None

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "target_capability": self.target_capability,
            "mutation": self.mutation,
            "parent": self.parent,
            "score": self.score,
            "retained": self.retained,
            "proposed_at": self.proposed_at,
            "council_receipt": self.council_receipt,
        }


class ASIEvolveHive:
    """Protocol hive that learns across all SOV3 hives via telemetry."""

    def __init__(self):
        self.candidates: list[HarnessCandidate] = []
        self._telemetry_snapshot: dict[str, Any] | None = None
        self._last_tick = 0.0

    def tick(self) -> dict[str, Any]:
        """One evolution tick: read telemetry, propose candidate, score, submit to Council."""
        self._telemetry_snapshot = telemetry.aggregate(window_seconds=3600)
        self._last_tick = time.time()

        # Propose a candidate based on the weakest capability signal.
        candidate = self._propose_candidate()
        self.candidates.append(candidate)

        # Sandbox scoring (stub: real implementation runs the harness in a sandbox).
        candidate.score = self._score_candidate(candidate)

        # Council gate: only candidates above the safety/capability bar proceed.
        # Phase 3 uses a local quorum stub; Phase 4 wires to SOV3 BFT 22/33.
        verdict = self._council_gate(candidate)
        candidate.retained = verdict.get("retained", False)
        candidate.council_receipt = verdict.get("receipt")

        # SIGIL record every tick.
        sigil.record({
            "op": "S",
            "tier": "warm",
            "fields": {
                "hive": "asi-evolve",
                "candidate": candidate.id,
                "target": candidate.target_capability,
                "score": str(candidate.score) if candidate.score is not None else "none",
                "retained": str(candidate.retained),
                "receipt": candidate.council_receipt or "-",
            },
        })

        return {
            "tick": len(self.candidates),
            "candidate": candidate.summary(),
            "telemetry_hives": list(self._telemetry_snapshot.get("hives", {}).keys()),
        }

    def _propose_candidate(self) -> HarnessCandidate:
        """Pick the weakest cross-hive capability and propose a harness mutation."""
        hives = (self._telemetry_snapshot or {}).get("hives", {})
        target = "general"
        if hives:
            # Choose the hive with the lowest safe ratio as the target capability.
            weakest = min(
                hives.items(),
                key=lambda item: item[1].get("safe", 0) / max(item[1].get("events", 1), 1),
            )
            target = weakest[0]
        cid = "h" + hashlib.sha256(f"{target}:{time.time()}".encode()).hexdigest()[:12]
        mutations = [
            "refine_prompt_template",
            "add_regression_test",
            "tune_temperature",
            "swap_router_model",
        ]
        mutation = mutations[len(self.candidates) % len(mutations)]
        parent = self.candidates[-1].id if self.candidates else None
        return HarnessCandidate(id=cid, target_capability=target, mutation=mutation, parent=parent)

    def _score_candidate(self, candidate: HarnessCandidate) -> float:
        """Sandbox score: higher is better. Stub uses telemetry heuristics."""
        hives = (self._telemetry_snapshot or {}).get("hives", {})
        base = 0.5
        if candidate.target_capability in hives:
            hive = hives[candidate.target_capability]
            events = hive.get("events", 1)
            safe_ratio = hive.get("safe", 0) / max(events, 1)
            latency = hive.get("avg_latency_ms") or 250
            base = safe_ratio * 0.7 + max(0, 1 - latency / 1000) * 0.3
        # Mutation novelty bonus.
        base += min(0.1, len(self.candidates) * 0.01)
        return round(base, 3)

    def _council_gate(self, candidate: HarnessCandidate) -> dict[str, Any]:
        """Local quorum stub. Returns {retained, receipt}."""
        # Threshold: score > 0.6 and no unsafe telemetry signal on target capability.
        hives = (self._telemetry_snapshot or {}).get("hives", {})
        target = hives.get(candidate.target_capability, {})
        unsafe = target.get("unsafe", 0)
        retained = bool(candidate.score and candidate.score > 0.6 and unsafe == 0)
        receipt = sigil.record({
            "op": "V",
            "agent": "asi-evolve-council-stub",
            "prop": candidate.id,
            "choice": "approve" if retained else "veto",
            "conf": str(candidate.score or 0.0),
        }).get("receipt", "-")
        return {"retained": retained, "receipt": receipt}

    def status(self) -> dict[str, Any]:
        return {
            "status": "running",
            "candidates_total": len(self.candidates),
            "candidates_retained": sum(1 for c in self.candidates if c.retained),
            "last_tick": self._last_tick,
            "telemetry_hives": list((self._telemetry_snapshot or {}).get("hives", {}).keys()),
        }


# Singleton for the process.
_EVOLVE = ASIEvolveHive()


def tick() -> dict[str, Any]:
    return _EVOLVE.tick()


def status() -> dict[str, Any]:
    return _EVOLVE.status()
