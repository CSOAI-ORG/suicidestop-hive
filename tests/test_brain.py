"""Tests for the MEOK ONE brain bridge. Run: python3 tests/test_brain.py
Works offline (SOV3 down) via the honest fallback; if SOV3 is up, also live-checks."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from meok_one.brain import Character, talk, _call_sov3  # noqa: E402


def test_character_loads_persona():
    aria = Character("aria")
    sp = aria.system_prompt()
    assert "Aria" in sp and "care coordinator" in sp.lower()


def test_system_prompt_has_length_nudge():
    assert "sentences" in Character("aria").system_prompt().lower()


def test_say_returns_shape():
    out = talk("aria", "hello")
    assert set(out) >= {"character", "id", "reply", "source", "emoji"}
    assert out["id"] == "aria" and out["emoji"] == "🌸"


def test_offline_fallback_is_honest():
    # point at a dead port to force the fallback
    import meok_one.brain as b
    orig = b.SOV3_MCP
    b.SOV3_MCP = "http://localhost:59999/mcp"
    try:
        out = talk("marcus", "hi")
        assert out["source"] == "offline-stub"
        assert "offline" in out["reply"].lower()  # never fabricates a model reply
    finally:
        b.SOV3_MCP = orig


def test_different_characters_different_persona():
    assert Character("aria").system_prompt() != Character("marcus").system_prompt()


def test_unknown_character_raises():
    try:
        Character("nope"); assert False
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
    # bonus: live check if SOV3 is up
    live = _call_sov3("nemotron_chat", {"message": "hi", "system_prompt": "Reply 'ok'.", "max_tokens": 10})
    print(f"\n  [live SOV3] {'reachable ✓' if live else 'offline (fallback path used)'}")
    print(f"{passed}/{len(fns)} tests passed")
    return passed == len(fns)


if __name__ == "__main__":
    raise SystemExit(0 if _run() else 1)
