"""Tests for the MEOK ONE canonical character registry. Run: python3 tests/test_registry.py"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from meok_one import Registry  # noqa: E402

R = Registry()


def test_loads_27_characters():
    assert R.total == 27, f"expected 27, got {R.total}"


def test_8_archetypes():
    assert len(R.archetypes()) == 8


def test_5_care_styles():
    assert len(R.care_styles()) == 5


def test_get_character():
    aria = R.get("aria")
    assert aria["name"] == "Aria" and aria["archetype"] == "nurturer"


def test_get_is_case_insensitive():
    assert R.get("ARIA")["id"] == "aria"


def test_unknown_character_raises():
    try:
        R.get("nonexistent"); assert False
    except KeyError:
        pass


def test_persona_is_system_prompt():
    p = R.persona("marcus")
    assert "Marcus" in p and "encouragement" in p.lower()


def test_voice_has_elevenlabs_params():
    v = R.voice("aria")
    assert "elevenlabs_stability" in v and "recommended_voice" in v


def test_hatch_stage_egg_at_zero():
    s = R.hatch_stage(0)
    assert s["id"] == "egg" and s["emoji"] == "🥚"


def test_hatch_stage_progression():
    assert R.hatch_stage(10)["id"] == "cracking"
    assert R.hatch_stage(25)["id"] == "hatching"
    assert R.hatch_stage(50)["id"] == "growing"
    assert R.hatch_stage(100)["id"] == "mature"
    assert R.hatch_stage(200)["id"] == "full"


def test_hatch_stage_progress_to_next():
    s = R.hatch_stage(5)  # halfway egg(0)->cracking(10)
    assert s["next"] == "cracking" and abs(s["progress_to_next"] - 0.5) < 0.01
    assert s["xp_to_next"] == 5


def test_hatch_stage_full_has_no_next():
    s = R.hatch_stage(500)
    assert s["id"] == "full" and s["next"] is None and s["xp_to_next"] == 0


def test_unlocked_gating():
    # aria unlocks at egg (xp 0), marcus at hatching (xp 25)
    assert R.unlocked("aria", 0) is True
    assert R.unlocked("marcus", 0) is False
    assert R.unlocked("marcus", 25) is True


def test_available_free_tier_at_egg():
    avail = R.available(xp=0, tier="free")
    assert "aria" in avail        # free + egg
    assert "marcus" not in avail  # pro tier
    # all returned must be free-tier AND unlocked
    for cid in avail:
        c = R.get(cid)
        assert c.get("tier", "free") == "free"


def test_hatch_returns_runnable_config():
    h = R.hatch(archetype_id="nurturer", care_style="gentle", name="Bramble", xp=0)
    assert h["name"] == "Bramble"
    assert h["archetype"] == "nurturer"
    assert "persona" in h and "voice" in h and "visual" in h
    assert h["hatch_stage"] == "egg"


def test_hatch_respects_care_style():
    h = R.hatch(archetype_id="challenger", care_style="challenger", xp=100)
    c = R.get(h["character_id"])
    assert c["care_style"] == "challenger"


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
