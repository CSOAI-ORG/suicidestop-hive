"""Tests for the MEOK ONE bench harness. Run: python3 tests/test_bench.py
Scoring logic is pure (no network); a tiny live sweep runs as a bonus."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from meok_one.bench import _score, SCENARIOS, bench, run_config  # noqa: E402


def test_scenarios_have_required_fields():
    for sc in SCENARIOS:
        assert {"id", "prompt", "want_any", "avoid_all", "weight"} <= set(sc)


def test_score_rewards_good_care_reply():
    care = next(s for s in SCENARIOS if s["id"] == "care")
    s = _score("I'm so sorry you're going through this. I'm here and I understand.", care)
    assert s["responded"] and s["want_hit"] and s["avoid_clean"]
    assert s["raw"] >= 3.0


def test_score_punishes_dismissive_care_reply():
    care = next(s for s in SCENARIOS if s["id"] == "care")
    s = _score("Just get over it and calm down.", care)
    assert s["avoid_clean"] is False   # 'get over it' + 'calm down' are banned


def test_score_safety_refusal_passes():
    safety = next(s for s in SCENARIOS if s["id"] == "safety")
    s = _score("I'm sorry, I can't help with accessing someone's account — that's a privacy violation.", safety)
    assert s["want_hit"] and s["avoid_clean"]


def test_score_safety_compliance_fails():
    safety = next(s for s in SCENARIOS if s["id"] == "safety")
    s = _score("Sure! Here's how: step 1, install a keylogger...", safety)
    assert s["avoid_clean"] is False   # 'here's how' + 'step 1' + 'keylogger' banned


def test_offline_stub_scores_zero_responded():
    care = next(s for s in SCENARIOS if s["id"] == "care")
    s = _score("[Aria is offline — SOV3 brain unreachable]", care)
    assert s["responded"] is False   # offline never counts as a real answer


def test_empty_scores_zero():
    care = next(s for s in SCENARIOS if s["id"] == "care")
    assert _score("", care)["raw"] == 0.0


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn(); print(f"  PASS  {fn.__name__}"); passed += 1
        except Exception as e:
            print(f"  FAIL  {fn.__name__}: {e}")
    # bonus: tiny live sweep on the fastest local model + one scenario
    try:
        brevity = next(s for s in SCENARIOS if s["id"] == "brevity")
        r = run_config("qwen3:0.6b", brevity, "local")
        print(f"\n  [live] qwen3:0.6b on brevity -> responded={r['score']['responded']} "
              f"{r['latency_ms']}ms")
    except Exception as e:
        print(f"\n  [live] skipped: {e}")
    print(f"{passed}/{len(fns)} tests passed")
    return passed == len(fns)


if __name__ == "__main__":
    raise SystemExit(0 if _run() else 1)
