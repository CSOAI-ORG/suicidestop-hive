"""Tests for the MEOK ONE model router. Run: python3 tests/test_router.py
Pure/offline-safe: forces backends to dead endpoints so logic is deterministic.
Live local-Ollama is checked as a bonus if :11434 answers."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import meok_one.router as R  # noqa: E402
from meok_one.router import ask, list_models, MODELS, _strip_thinking  # noqa: E402


def test_models_cover_all_backends():
    backends = {b for b, _ in MODELS.values()}
    assert backends == {"local", "sov3", "cloud"}


def test_list_models_local_is_local_only():
    ids = [m["backend"] for m in list_models("local")]
    assert ids and set(ids) == {"local"}


def test_list_models_pro_has_cloud():
    ids = [m["id"] for m in list_models("pro")]
    assert "gpt-4o" in ids and "qwen3:8b" in ids and "hermes" in ids


def test_unknown_model_errors():
    assert ask("hi", "no-such-model", "pro")["source"] == "error"


def test_tier_blocks_cloud_on_local():
    out = ask("hi", "gpt-4o", "local")
    assert out["source"] == "tier-blocked" and out["reply"] is None


def test_cloud_unconfigured_is_honest():
    # no OPENROUTER_API_KEY in test env -> must say so, not fabricate
    os.environ.pop("OPENROUTER_API_KEY", None)
    out = ask("hi", "gpt-4o", "pro")
    # backend tried = cloud; with no key it falls through to no-backend
    assert out["reply"] is None and out["source"] in ("no-backend", "cloud")


def test_strip_thinking():
    assert _strip_thinking("<think>x</think>Hi") == "Hi"
    assert _strip_thinking("plain") == "plain"


def test_no_backend_when_all_dead():
    # point local + sov3 at dead ports so nothing answers
    orig_o, orig_s = R.OLLAMA, R.SOV3_MCP
    R.OLLAMA = "http://localhost:59998"
    R.SOV3_MCP = "http://localhost:59999/mcp"
    os.environ.pop("OPENROUTER_API_KEY", None)
    try:
        out = ask("hi", "auto", "pro")
        assert out["reply"] is None and out["source"] == "no-backend"
    finally:
        R.OLLAMA, R.SOV3_MCP = orig_o, orig_s


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn(); print(f"  PASS  {fn.__name__}"); passed += 1
        except Exception as e:
            print(f"  FAIL  {fn.__name__}: {e}")
    # bonus live check
    live = ask("Reply with exactly: OK", "qwen3:0.6b", "local")
    print(f"\n  [live local Ollama] {'reachable: '+repr(live.get('reply'))[:40] if live.get('reply') else 'offline (logic tests still valid)'}")
    print(f"{passed}/{len(fns)} tests passed")
    return passed == len(fns)


if __name__ == "__main__":
    raise SystemExit(0 if _run() else 1)
