"""Tests for MEOK ONE voice layer. Run: python3 tests/test_voice.py
Offline-safe: voice_reply uses brain's honest offline stub when SOV3 is down."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import meok_one.brain as _b  # noqa: E402
_b.SOV3_MCP = "http://localhost:59999/mcp"  # force brain offline -> deterministic
from meok_one.voice import tts_spec, voice_reply, stt_hint  # noqa: E402


def test_tts_spec_uses_character_voice():
    s = tts_spec("aria", "hello")
    assert s["elevenlabs"]["recommended_voice"] == "Rachel"   # aria's registry voice
    assert s["text"] == "hello"


def test_distinct_characters_distinct_voices():
    assert (tts_spec("aria", "x")["elevenlabs"]["recommended_voice"]
            != tts_spec("marcus", "x")["elevenlabs"]["recommended_voice"])


def test_tts_spec_has_browser_fallback():
    s = tts_spec("aria", "x")
    assert "pitch" in s["browser_fallback"] and "rate" in s["browser_fallback"]
    assert s["engine_preference"][0] == "elevenlabs"


def test_voice_reply_bundles_text_and_tts():
    out = voice_reply("aria", "hi")
    assert "reply_text" in out and "tts" in out and "reply_source" in out
    assert out["tts"]["character"] == "Aria"


def test_voice_reply_is_honest_offline():
    out = voice_reply("aria", "hi")
    # brain forced offline -> source must be the honest stub, not fabricated audio
    assert out["reply_source"] == "offline-stub"


def test_stt_hint_is_browser_first():
    assert stt_hint()["preferred"] == "browser_web_speech_api"


def test_unknown_character_fails_loud():
    try:
        tts_spec("nope", "x"); assert False
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
    print(f"\n{passed}/{len(fns)} tests passed")
    return passed == len(fns)


if __name__ == "__main__":
    raise SystemExit(0 if _run() else 1)
