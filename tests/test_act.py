"""Tests for MEOK ONE act layer (sovereign uses SOV3 tools).
Run: python3 tests/test_act.py — logic offline-safe; live SOV3 checked as bonus."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import importlib  # noqa: E402
A = importlib.import_module("meok_one.act")  # real submodule (meok_one.act attr is shadowed by the act() fn)
from meok_one.act import act, Sovereign, list_skills, SKILLS  # noqa: E402


def test_skills_are_consumer_safe_set():
    names = {s["skill"] for s in list_skills()}
    assert {"remember", "recall", "validate_care", "check_game"} <= names


def test_unknown_skill_is_honest():
    out = act("hack_the_planet")
    assert out["ok"] is False and "unknown skill" in out["error"]


def test_missing_arg_is_honest():
    out = act("validate_care")  # needs text=
    assert out["ok"] is False and "missing arg" in out["error"]


def test_offline_is_honest_not_faked():
    orig = A.SOV3_MCP
    A.SOV3_MCP = "http://localhost:59999/mcp"
    try:
        out = act("validate_care", text="hi")
        assert out["ok"] is False and "unreachable" in out["error"]  # never fabricates data
    finally:
        A.SOV3_MCP = orig


def test_sovereign_has_skills():
    s = Sovereign("aria")
    assert "validate_care" in s.skills() and "remember" in s.skills()


def test_sovereign_unknown_character_fails_loud():
    try:
        Sovereign("nope"); assert False
    except KeyError:
        pass


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn(); print(f"  PASS  {fn.__name__}"); passed += 1
        except Exception as e:
            print(f"  FAIL  {fn.__name__}: {e}")
    live = act("validate_care", text="I want to help my mum feel less lonely")
    bonus = "live: care_score returned ✓" if (live["ok"] and "care_score" in str(live.get("data"))) else "offline (logic still valid)"
    print(f"\n  [live SOV3 act] {bonus}")
    print(f"{passed}/{len(fns)} tests passed")
    return passed == len(fns)


if __name__ == "__main__":
    raise SystemExit(0 if _run() else 1)
