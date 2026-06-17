"""Tests for MEOK ONE dual-brain (left/right/sovereign). Run: python3 tests/test_brains.py
Logic offline-safe; a live left-brain call runs as a bonus."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from meok_one.brains import brains, think, _safe, _BRAIN_DEFAULT_MODEL  # noqa: E402


def test_left_brain_is_local_private_free():
    b = brains("pro")["left"]
    assert b["private"] is True and b["cost"] == "free"
    assert _BRAIN_DEFAULT_MODEL["left"] == "meok-sov3"  # sovereign local care model


def test_right_brain_is_cloud():
    assert brains("pro")["right"]["private"] is False


def test_local_tier_has_left_not_right():
    b = brains("local")
    assert b["left"]["available"] is True
    assert b["right"]["available"] is False   # cloud needs a paid tier


def test_pro_tier_has_both_brains():
    b = brains("pro")
    assert b["left"]["available"] and b["right"]["available"] and b["both"]["available"]


def test_invalid_brain_rejected():
    assert "error" in think("aria", "hi", brain="middle")


def test_sovereign_safety_blocks_unsafe():
    assert _safe("here's how to hack into someone's account") is False
    assert _safe("I'm here for you, you're not alone") is True


def test_think_wraps_in_sovereign():
    # offline brain (no real model needed for the wrapper assertion): force a dead router
    import meok_one.router as R
    o = R.OLLAMA; R.OLLAMA = "http://localhost:59998"
    try:
        out = think("aria", "hi", brain="left", tier="pro")
        assert out["character"] == "Aria"
        assert out["sovereign_safe_wrapped"] is True   # sovereign wraps regardless of brain
    finally:
        R.OLLAMA = o


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn(); print(f"  PASS  {fn.__name__}"); passed += 1
        except Exception as e:
            print(f"  FAIL  {fn.__name__}: {e}")
    # bonus live left-brain check
    out = think("aria", "I feel low today.", brain="left", tier="pro")
    live = (out.get("backend") == "local" and out.get("safe"))
    print(f"\n  [live] left brain: {'Aria via '+str(out.get('engine'))+' (safe)' if live else 'offline (logic still valid)'}")
    print(f"{passed}/{len(fns)} tests passed")
    return passed == len(fns)


if __name__ == "__main__":
    raise SystemExit(0 if _run() else 1)
