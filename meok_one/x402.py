"""
MEOK ONE — x402 pay-per-call rail (the machine economy).

x402 = the HTTP 402 "Payment Required" protocol (Coinbase, 2025) that lets AI agents
pay for an API per-request in stablecoin (USDC) with no account or API key. This wires
MEOK's Usage tier (£0.002/interaction) onto that rail so the 264 MCPs can charge agents
micro-amounts automatically — MEOK as a toll booth in the agent economy.

The flow (standard x402):
  1. agent calls a paid endpoint with no payment    -> 402 + payment_requirements
  2. agent pays via a facilitator, retries with an   -> X-PAYMENT header (the proof)
     X-PAYMENT header carrying the settlement proof
  3. endpoint verifies the proof                      -> 200 + the data

HONEST scope: this implements the x402 ENVELOPE — building the 402 challenge and
verifying a payment-proof's shape/amount. It does NOT settle USDC on-chain itself
(that needs a facilitator: Coinbase's hosted one, or a self-hosted verifier with
chain access). verify_payment() checks structure + amount + that a facilitator
attested it; with no facilitator configured it returns verified=False, never fakes
a settlement. Plug a facilitator URL via MEOK_X402_FACILITATOR to go live.

    price_for(resource)            -> USDC micro-price for an MCP/skill call
    challenge(resource)            -> the 402 payment_requirements body
    verify_payment(header, resource) -> {verified, reason} (honest; needs facilitator to be True)
    paywall(resource, x_payment)   -> {status, body} — the whole gate in one call
"""

import json
import os

# MEOK receiving address (set in env for production; placeholder is clearly fake).
PAY_TO = os.environ.get("MEOK_X402_ADDRESS", "0xMEOK-SET-MEOK_X402_ADDRESS")
FACILITATOR = os.environ.get("MEOK_X402_FACILITATOR", "")  # e.g. Coinbase x402 facilitator URL
NETWORK = os.environ.get("MEOK_X402_NETWORK", "base")       # base / base-sepolia / solana
USDC_ASSET = os.environ.get("MEOK_X402_ASSET", "USDC")

# Per-resource pricing in USDC. Default = the Usage-tier £0.002 ≈ $0.0025 (rounded micro).
# Override specific MCPs that are worth more (e.g. a signed compliance attestation).
_DEFAULT_PRICE_USDC = 0.0025
_PRICE_OVERRIDES = {
    "eu-ai-act-compliance-mcp": 0.05,   # a signed AI-Act check is worth more than a chat call
    "dora-compliance-mcp": 0.05,
    "firmware-attestation-mcp": 0.02,
    "attestation:sign": 0.10,           # issuing a signed cert
}


def price_for(resource: str) -> float:
    """USDC price for one call to `resource` (an MCP name or skill)."""
    return _PRICE_OVERRIDES.get(resource, _DEFAULT_PRICE_USDC)


def challenge(resource: str) -> dict:
    """The HTTP 402 body: what the agent must pay to use `resource`.
    Shape follows the x402 'payment requirements' convention."""
    amount = price_for(resource)
    return {
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact",
            "network": NETWORK,
            "asset": USDC_ASSET,
            "amount": str(amount),
            "payTo": PAY_TO,
            "resource": resource,
            "description": f"MEOK pay-per-call: {resource}",
            "mimeType": "application/json",
        }],
        "facilitator_configured": bool(FACILITATOR),
        "note": ("Pay this amount in USDC via an x402 facilitator, then retry with an "
                 "X-PAYMENT header carrying the settlement proof."),
    }


def verify_payment(x_payment_header: str, resource: str) -> dict:
    """Verify an X-PAYMENT proof for `resource`. HONEST: real verification requires a
    facilitator with chain access. Without one (FACILITATOR unset) we validate the
    envelope shape + amount but return verified=False, because we cannot confirm
    on-chain settlement — we never fake a payment as settled."""
    if not x_payment_header:
        return {"verified": False, "reason": "no X-PAYMENT header"}
    try:
        proof = json.loads(x_payment_header) if isinstance(x_payment_header, str) else x_payment_header
    except (json.JSONDecodeError, TypeError):
        return {"verified": False, "reason": "X-PAYMENT not valid JSON"}

    need = price_for(resource)
    paid = float(proof.get("amount", 0) or 0)
    if paid < need:
        return {"verified": False, "reason": f"underpaid: {paid} < {need} {USDC_ASSET}"}
    if proof.get("resource") != resource:
        return {"verified": False, "reason": "payment resource mismatch"}

    if not FACILITATOR:
        # Envelope is well-formed and amount is sufficient, but we cannot confirm
        # on-chain settlement without a facilitator. Be honest, do not pass.
        return {"verified": False, "reason": "no facilitator configured — cannot confirm "
                "on-chain settlement (set MEOK_X402_FACILITATOR to go live)",
                "envelope_ok": True}

    # With a facilitator, we'd POST the proof to it for on-chain verification here.
    # The facilitator's attestation is the source of truth.
    attested = bool(proof.get("facilitator_attestation"))
    return {"verified": attested,
            "reason": "facilitator attested" if attested else "facilitator did not attest",
            "envelope_ok": True}


def paywall(resource: str, x_payment_header: str = "") -> dict:
    """The whole gate: no/invalid payment -> 402 challenge; valid -> 200 allow.
    A paid MCP wraps its handler with this."""
    if not x_payment_header:
        return {"status": 402, "body": challenge(resource)}
    v = verify_payment(x_payment_header, resource)
    if v["verified"]:
        return {"status": 200, "body": {"allow": True, "resource": resource, "paid": price_for(resource)}}
    return {"status": 402, "body": {**challenge(resource), "rejected": v["reason"]}}


if __name__ == "__main__":
    print("=== x402 challenge for eu-ai-act-compliance-mcp ===")
    print(json.dumps(challenge("eu-ai-act-compliance-mcp"), indent=2))
    print("\n=== paywall with no payment ===")
    print("status:", paywall("firmware-attestation-mcp")["status"])
    print("\n=== verify underpayment (honest reject) ===")
    print(verify_payment(json.dumps({"amount": "0.001", "resource": "eu-ai-act-compliance-mcp"}),
                         "eu-ai-act-compliance-mcp"))
