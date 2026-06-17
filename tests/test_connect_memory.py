"""Tests for MEOK CONNECT + MEMORY. Run: python3 tests/test_connect_memory.py
Forces offline memory so tests are deterministic with or without SOV3."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import meok_one.memory as _m  # noqa: E402
_m.SOV3_MCP = "http://localhost:59999/mcp"  # force offline -> deterministic
from meok_one.memory import MemoryBridge  # noqa: E402
from meok_one.connect import connect, remember, integration_spec  # noqa: E402


# ---- MEMORY ----
def test_record_offline_is_honest():
    out = MemoryBridge().record("u1", "likes tea", platform="claude")
    assert out["stored"] is False and out["source"] == "offline-stub"  # never fakes storage


def test_recall_offline_returns_empty_not_fabricated():
    out = MemoryBridge().recall("u1", "drinks")
    assert out["memories"] == [] and out["source"] == "offline-stub"


def test_export_is_gdpr_art20():
    out = MemoryBridge().export("u1")
    assert "Art 20" in out["right"]


def test_forget_is_honest_about_not_deleting_yet():
    out = MemoryBridge().forget("u1")
    # MUST NOT claim deletion it didn't perform (GDPR honesty)
    assert out["deleted"] is False and out["status"] == "pending"


def test_per_user_namespacing():
    # the tag isolates users
    assert _m._tag("alice") != _m._tag("bob")


# ---- CONNECT ----
def test_connect_returns_ingredients_not_reply():
    env = connect("aria", "u1", "hello", platform="consumer")
    assert "system_prompt" in env and "memory_context" in env and "safety_policy" in env
    assert "reply" not in env  # MEOK never generates the reply — the platform does


def test_connect_is_model_agnostic():
    env = connect("aria", "u1", "hi")
    assert env["meta"]["model_agnostic"] is True
    assert env["meta"]["meok_runs_the_llm"] is False


def test_system_prompt_carries_persona():
    env = connect("marcus", "u1", "push me")
    assert "Marcus" in env["system_prompt"] and "SAFETY:" in env["system_prompt"]


def test_game_platform_applies_age_gate():
    env = connect("pixel", "u1", "let's play", platform="game", age_rating="E")
    assert env["safety_policy"]["age_rating"] == "E"
    assert env["safety_policy"]["age_gate"] is not None
    assert "AGE GATE" in env["system_prompt"]


def test_enterprise_platform_sets_audit():
    env = connect("atlas", "u1", "plan our Q3", platform="enterprise")
    assert env["safety_policy"]["audit"] is True


def test_unknown_character_fails_loud():
    try:
        connect("nope", "u1", "hi"); assert False
    except KeyError:
        pass


def test_remember_offline_is_honest():
    out = remember("u1", "hi", "hello there", platform="kimiclaw")
    assert out["stored"] is False and out["source"] == "offline-stub"


def test_integration_spec_is_handable():
    spec = integration_spec()
    assert spec["meok_provides"] and "any LLM" in spec["you_provide"]
    assert "consumer" in spec["platforms"] and "game" in spec["platforms"]


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
