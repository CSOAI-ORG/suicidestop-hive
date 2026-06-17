"""Tests for MEOK ONE tiers/billing + tier-gating in connect.
Run: python3 tests/test_tiers.py"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import meok_one.memory as _m  # noqa: E402
_m.SOV3_MCP = "http://localhost:59999/mcp"  # offline -> deterministic
from meok_one.tiers import (TIERS, get_tier, can_hatch, quote,  # noqa: E402
                            entitlements, ladder)
from meok_one.connect import connect  # noqa: E402


# ---- the ladder (Nick's decisions) ----
def test_all_tiers_exist():
    assert set(TIERS) == {"local", "free", "pro", "professional", "usage", "enterprise"}


def test_local_is_free_selfhost_oss():
    t = get_tier("local")
    assert t.hosting == "self" and t.open_source is True
    assert (t.price_gbp_month or 0) == 0 and t.per_interaction_gbp is None


def test_usage_is_per_interaction():
    t = get_tier("usage")
    assert t.per_interaction_gbp == 0.002 and t.price_gbp_month is None


def test_enterprise_has_everything():
    t = get_tier("enterprise")
    assert t.attestation and t.audit_trail and t.reggeoint


def test_quote_usage_math_is_honest():
    q = quote("usage", 500_000)
    assert q["usage_gbp"] == 1000.0 and q["total_gbp_month"] == 1000.0


def test_quote_local_is_free():
    assert quote("local", 999999)["free"] is True


def test_can_hatch_gating():
    assert can_hatch("free", "free") is True
    assert can_hatch("free", "pro") is False     # free tier can't hatch pro characters
    assert can_hatch("pro", "pro") is True
    assert can_hatch("enterprise", "gaming") is True


def test_ladder_renders_all_six():
    rows = ladder()
    assert len(rows) == 6 and rows[0]["id"] == "local" and rows[-1]["id"] == "enterprise"


def test_unknown_tier_fails_loud():
    try:
        get_tier("nope"); assert False
    except KeyError:
        pass


# ---- tier gating flows through connect ----
def test_local_tier_no_cross_platform_memory():
    env = connect("aria", "u1", "hi", tier="local")
    assert env["billing"]["memory_cross_platform"] is False
    assert env["billing"]["hosting"] == "self"
    assert env["memory_context"] == ""   # local = no hosted memory injected


def test_free_tier_has_memory_no_attestation():
    env = connect("aria", "u1", "hi", tier="free")
    assert env["billing"]["memory_cross_platform"] is True
    assert env["billing"]["attestation"] is False


def test_enterprise_tier_unlocks_everything():
    env = connect("atlas", "u1", "plan", platform="enterprise", tier="enterprise")
    b = env["billing"]
    assert b["attestation"] and b["audit_trail"] and b["reggeoint"]
    assert env["safety_policy"]["audit"] is True


def test_usage_tier_audits():
    env = connect("aria", "u1", "hi", tier="usage")
    assert env["billing"]["audit_trail"] is True


def test_connect_unknown_tier_fails_loud():
    try:
        connect("aria", "u1", "hi", tier="bogus"); assert False
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
