"""Tests for MEOK ONE x402 pay-per-call rail. Run: python3 tests/test_x402.py
Pure logic (no chain/network). Verifies the envelope + honest no-settlement behaviour."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import meok_one.x402 as X  # noqa: E402
from meok_one.x402 import price_for, challenge, verify_payment, paywall  # noqa: E402


def test_default_and_override_pricing():
    assert price_for("random-mcp") == 0.0025
    assert price_for("eu-ai-act-compliance-mcp") == 0.05


def test_challenge_is_x402_shaped():
    c = challenge("firmware-attestation-mcp")
    assert c["x402Version"] == 1
    acc = c["accepts"][0]
    assert acc["asset"] == "USDC" and acc["resource"] == "firmware-attestation-mcp"
    assert acc["amount"] == "0.02"


def test_paywall_no_payment_is_402():
    assert paywall("any-mcp")["status"] == 402


def test_underpayment_rejected():
    proof = json.dumps({"amount": "0.001", "resource": "eu-ai-act-compliance-mcp"})
    assert verify_payment(proof, "eu-ai-act-compliance-mcp")["verified"] is False


def test_resource_mismatch_rejected():
    proof = json.dumps({"amount": "1.0", "resource": "other-mcp"})
    assert verify_payment(proof, "eu-ai-act-compliance-mcp")["verified"] is False


def test_no_facilitator_does_not_fake_settlement():
    # sufficient amount + right resource, but no facilitator -> must NOT verify
    X.FACILITATOR = ""
    proof = json.dumps({"amount": "0.10", "resource": "attestation:sign"})
    out = verify_payment(proof, "attestation:sign")
    assert out["verified"] is False and out.get("envelope_ok") is True
    assert "facilitator" in out["reason"]


def test_facilitator_attestation_path():
    X.FACILITATOR = "https://facilitator.example/verify"
    try:
        ok = json.dumps({"amount": "0.10", "resource": "attestation:sign",
                         "facilitator_attestation": True})
        no = json.dumps({"amount": "0.10", "resource": "attestation:sign"})
        assert verify_payment(ok, "attestation:sign")["verified"] is True
        assert verify_payment(no, "attestation:sign")["verified"] is False
    finally:
        X.FACILITATOR = ""


def test_bad_header_is_honest():
    assert verify_payment("not-json", "x")["verified"] is False
    assert verify_payment("", "x")["verified"] is False


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
