"""Tests for MEOK ONE capability awareness. Run: python3 tests/test_capabilities.py
Logic is offline-safe (discovery returns [] when SOV3 is down — never fabricates)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import meok_one.capabilities as C  # noqa: E402
from meok_one.capabilities import discover, awareness_brief, _group, _BRIDGES  # noqa: E402


def test_bridges_include_browser_and_dynamic():
    assert "browser" in _BRIDGES and "dynamic_tools" in _BRIDGES


def test_brief_tells_character_it_can_browse():
    b = awareness_brief("pro")
    assert "browser" in b.lower()
    assert "can drive" in b.lower() or "Use the bridge" in b  # the anti-"I can't" line


def test_brief_warns_against_assuming_limited_tools():
    b = awareness_brief("pro")
    assert "mcp_bridge_discover" in b  # told how to find MORE at runtime


def test_grouping_buckets_tools():
    g = _group(["record_memory", "query_memories", "guardian_moderate_chat",
                "submit_council_proposal", "some_random_tool"])
    assert "memory" in g and "council" in g and "safety/guardian" in g
    assert "other" in g and "some_random_tool" in g["other"]


def test_discover_offline_is_honest():
    orig = C.SOV3_MCP
    C.SOV3_MCP = "http://localhost:59999/mcp"
    try:
        cap = discover("free")
        assert cap["sov3_online"] is False and cap["tool_count"] == 0
        # brief still works offline — bridges are always known
        b = awareness_brief("free")
        assert "browser" in b.lower()
    finally:
        C.SOV3_MCP = orig


def test_connect_injects_capabilities():
    from meok_one.connect import connect
    env = connect("aria", "u1", "check a site", tier="pro")
    assert "LIVE CAPABILITIES" in env["system_prompt"]


def test_connect_capabilities_can_be_disabled():
    from meok_one.connect import connect
    env = connect("aria", "u1", "hi", tier="pro", with_capabilities=False)
    assert "LIVE CAPABILITIES" not in env["system_prompt"]


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn(); print(f"  PASS  {fn.__name__}"); passed += 1
        except Exception as e:
            print(f"  FAIL  {fn.__name__}: {e}")
    live = discover("pro")
    print(f"\n  [live] SOV3 {'online: '+str(live['tool_count'])+' tools' if live['sov3_online'] else 'offline (logic still valid)'}")
    print(f"{passed}/{len(fns)} tests passed")
    return passed == len(fns)


if __name__ == "__main__":
    raise SystemExit(0 if _run() else 1)
