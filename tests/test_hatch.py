"""Tests for the MEOK ONE hatch flow. Run: python3 tests/test_hatch.py
Uses offline brain fallback so it passes with or without SOV3."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import meok_one.brain as _b  # noqa: E402
_b.SOV3_MCP = "http://localhost:59999/mcp"  # force offline so tests are deterministic
from meok_one.hatch import HatchSession, hatch_session  # noqa: E402


def test_options_shows_8_archetypes_5_styles():
    o = HatchSession().options()
    assert len(o["archetypes"]) == 8 and len(o["care_styles"]) == 5


def test_hatch_returns_reveal():
    s = HatchSession()
    r = s.hatch("nurturer", "gentle", "Bramble")
    assert r["hatched"] and r["name"] == "Bramble"
    assert r["stage"] == "egg" and r["stage_emoji"] == "🥚"
    assert s.character is not None


def test_cannot_talk_before_hatch():
    try:
        HatchSession().talk("hi"); assert False
    except RuntimeError:
        pass


def test_xp_accrues_and_levels_up():
    s = HatchSession()
    s.hatch("nurturer", "gentle", "Bramble")
    s.talk("one")              # xp 5  -> egg
    out = s.talk("two")        # xp 10 -> cracking
    assert out["xp"] == 10 and out["stage"] == "cracking" and out["leveled_up"] is True


def test_full_session_transcript():
    t = hatch_session("challenger", "challenger", "Forge", ["push me", "again"])
    assert t["reveal"]["archetype"] == "challenger"
    assert len(t["exchanges"]) == 2
    assert t["final_xp"] == 10


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn(); print(f"  PASS  {fn.__name__}"); passed += 1
        except Exception as e:
            print(f"  FAIL  {fn.__name__}: {e}")
    print(f"\n{passed}/{len(fns)} tests passed")
    return passed == len(fns)


if __name__ == "__main__":
    raise SystemExit(0 if _run() else 1)
