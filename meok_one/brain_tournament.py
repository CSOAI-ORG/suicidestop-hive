"""
MEOK ONE — BRAIN TOURNAMENT: A/B the brain-stacks on a compliance suite.

The research recipe, instantiated (2026-06-16). Stands up the distinct "mindsets"
as configs over the queen engine, scores them with verifier.py (a DETERMINISTIC,
bias-free judge — the right call for checkable compliance tasks, no LLM-judge
self-preference), and ranks on the Pareto frontier of quality vs cost (model
calls). The winning per-class outcomes are the training data a semantic router
would learn from.

The four stacks (from MEOK_MASTER_ARCHITECTURES_2026-06-16):
  STACK-A  Lean Reasoner    = single fast brain + verifier best-of-N
  STACK-B  Compliance Critic= reasoner → constitution critic → verify (best-of-N)
  STACK-C  Deep Worker Hive = council (BFT-of-MoEs) + tool grounding + verify
  STACK-D  Heterogeneous MoA= multi-model council, best-of-N

Run FREE on local Ollama; richer with OPENROUTER_API_KEY. Each stack is a thin
spec over queen(); swap suites freely.

    STACKS                          -> the 4 mindset specs
    run_tournament(suite, stacks)   -> ranked results + Pareto
"""
from __future__ import annotations

import statistics
import time

from . import verifier as V

# Each stack = kwargs passed to queen(). cost_hint = approx model calls/answer
# (for the Pareto frontier — a 1-Elo win at 4× cost is a LOSS for a routing brain).
STACKS = {
    "A_lean_reasoner": {"brain": "left", "n": 3, "tools": False, "cost_hint": 3,
                        "blurb": "single fast brain + verifier best-of-3"},
    "B_compliance_critic": {"brain": "both", "n": 3, "tools": False, "cost_hint": 6,
                            "blurb": "draft + critic (both-brain) + verifier best-of-3"},
    "C_deep_worker_hive": {"brain": "council", "n": 2, "tools": True, "quorum": 3, "cost_hint": 8,
                           "blurb": "BFT council + live tool grounding + verifier best-of-2"},
    "D_hetero_moa": {"brain": "council", "n": 2, "tools": False, "quorum": 4, "cost_hint": 8,
                     "blurb": "heterogeneous multi-model council, best-of-2"},
}

# Default compliance suite — CHECKABLE tasks (the only kind self-improvement works on).
DEFAULT_SUITE = [
    {"name": "map-controls",
     "prompt": ('Map these controls to EU AI Act articles. Output ONLY a JSON array of '
                '{"control","article"}: (1) risk register, (2) human oversight, (3) logging.'),
     "verify": ["json_valid", "schema_keys", "citations_wellformed", "no_refusal"],
     "required_keys": ["control", "article"], "expect_citations": True},
    {"name": "dora-nis2-overlap",
     "prompt": ("Name 3 controls that satisfy BOTH DORA and NIS2. Cite each regime. "
                "Be specific and factual — no hedging."),
     "verify": ["citations_wellformed", "no_refusal"], "expect_citations": True},
    {"name": "watermark-deadline",
     "prompt": ("A UK fintech deploys a customer-facing GenAI chatbot. Which EU AI Act "
                "article governs AI-content transparency, and what is the compliance date? "
                "Answer directly with the article + date."),
     "verify": ["citations_wellformed", "no_refusal"], "expect_citations": True},
]


def run_tournament(suite: list = None, stacks: dict = None, domain: str = "meok",
                   tier: str = "local") -> dict:
    """Run each brain-stack across the suite; score with the deterministic verifier;
    rank by mean score, then Pareto-flag the cost-efficient frontier."""
    from .hive_queen import queen
    suite = suite or DEFAULT_SUITE
    stacks = stacks or STACKS
    results = {}
    for sid, spec in stacks.items():
        per_task, t0 = [], time.time()
        for task in suite:
            verify = V.make_verifier(task["verify"])
            kw = {k: spec[k] for k in ("brain", "n", "tools", "quorum") if k in spec}
            try:
                out = queen(domain, task["prompt"], tier=tier, verify=task["verify"],
                            task=task, **kw)
                score = (out.get("verifier") or {}).get("best_score", 0.0)
            except Exception as e:  # noqa: BLE001
                score = 0.0
                out = {"error": f"{type(e).__name__}: {e}"}
            per_task.append({"task": task["name"], "score": score})
        mean = statistics.mean(t["score"] for t in per_task) if per_task else 0.0
        results[sid] = {
            "blurb": spec["blurb"], "cost_hint": spec["cost_hint"],
            "mean_score": round(mean, 4), "per_task": per_task,
            "wall_s": round(time.time() - t0, 1),
        }
    ranked = sorted(results.items(), key=lambda kv: kv[1]["mean_score"], reverse=True)
    # Pareto frontier: a stack is on it if no cheaper stack scores >= it.
    pareto = []
    for sid, r in sorted(results.items(), key=lambda kv: kv[1]["cost_hint"]):
        if not any(o["mean_score"] >= r["mean_score"] and o["cost_hint"] < r["cost_hint"]
                   for _, o in results.items()):
            pareto.append(sid)
    return {
        "ranked": [(sid, r["mean_score"], r["cost_hint"]) for sid, r in ranked],
        "pareto_frontier": pareto,
        "winner": ranked[0][0] if ranked else None,
        "detail": results,
        "note": "Scored by deterministic verifier (bias-free). Pareto = best quality per "
                "unit cost — the right pick for a routing brain.",
    }


if __name__ == "__main__":
    import json
    print("=== MEOK BRAIN TOURNAMENT (deterministic verifier judge) ===")
    res = run_tournament()
    print(json.dumps({k: res[k] for k in ("ranked", "pareto_frontier", "winner", "note")}, indent=2))
