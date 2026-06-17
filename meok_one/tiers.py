"""
MEOK ONE — Tiers & Billing (Nick's business-model decisions, encoded).

The deliberate "everyone eats" ladder:

  LOCAL    free, self-host, open-source basic — runs on the user's own machine,
           their own LLM (Ollama). MEOK earns nothing here on purpose: this is the
           adoption engine + the "you truly own it" proof. No usage caps, no phone-home.
  FREE     hosted free tier — one hatched character, free-tier characters only,
           capped interactions/day. The consumer on-ramp.
  PRO      paid flat — all characters, cross-platform memory, higher caps.
  USAGE    paid-per-interaction — for AI companies / games embedding MEOK at scale
           via CONNECT. This is where the big platforms "eat" alongside us.
  ENTERPRISE  paid + attestation + audit trail + RegGeoInt compliance map. Per-seat/contract.

Why this shape (decisions 1 + 3): big AI companies adopt USAGE/ENTERPRISE (we eat together
on paid); anyone wary self-hosts LOCAL for free (their cost, their control) — which still
grows the network + the standard. Nobody is locked out; the paid tiers are where revenue is.

Pure stdlib. Prices are defined here as the single source of truth; Stripe links live
elsewhere and should reference these IDs.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Tier:
    id: str
    label: str
    price_gbp_month: Optional[float]      # None = free; 0.0 also free
    per_interaction_gbp: Optional[float]  # None = not usage-billed
    hosting: str                          # "self" (local) or "meok"
    characters: str                       # "free-only" | "all" | "all+custom"
    memory_cross_platform: bool
    daily_interaction_cap: Optional[int]  # None = uncapped
    attestation: bool                     # signed receipts (proofof.ai) — the GDPR-proof layer
    audit_trail: bool                     # hash-chained audit (EU AI Act Art 12)
    reggeoint: bool                       # compliance-map access
    open_source: bool
    who: str                              # who this tier is for
    notes: str = ""


# THE LADDER — single source of truth
TIERS = {
    "local": Tier(
        id="local", label="Local (self-host, OSS)", price_gbp_month=None,
        per_interaction_gbp=None, hosting="self", characters="all",
        memory_cross_platform=False,  # local memory only — it's on their machine
        daily_interaction_cap=None, attestation=False, audit_trail=True,
        reggeoint=False, open_source=True,
        who="privacy-first users, devs, anyone wary of a hosted vault",
        notes="Free forever. Their machine, their LLM (Ollama), their data. The adoption "
              "engine + the ultimate 'you own it' proof. MEOK earns nothing here by design."),
    "free": Tier(
        id="free", label="Free (hosted)", price_gbp_month=0.0,
        per_interaction_gbp=None, hosting="meok", characters="free-only",
        memory_cross_platform=True, daily_interaction_cap=50, attestation=False,
        audit_trail=False, reggeoint=False, open_source=False,
        who="consumers trying it",
        notes="One hatched care-director, free-tier characters, 50 msgs/day. The on-ramp."),
    "pro": Tier(
        id="pro", label="Compliance Pro", price_gbp_month=79.0,
        per_interaction_gbp=None, hosting="meok", characters="all",
        memory_cross_platform=True, daily_interaction_cap=10000, attestation=True,
        audit_trail=True, reggeoint=False, open_source=False,
        who="SMEs, compliance teams",
        notes="Unlimited interactions across 28 hives, signed attestations, Article 50 ready."),
    "professional": Tier(
        id="professional", label="Professional", price_gbp_month=199.0,
        per_interaction_gbp=None, hosting="meok", characters="all",
        memory_cross_platform=True, daily_interaction_cap=50000, attestation=True,
        audit_trail=True, reggeoint=True, open_source=False,
        who="Consultants, mid-market",
        notes="Advanced transparency + bias detection, 12-framework crosswalk, custom verify domain."),
    "usage": Tier(
        id="usage", label="Usage (platform embed)", price_gbp_month=None,
        per_interaction_gbp=0.002, hosting="meok", characters="all+custom",
        memory_cross_platform=True, daily_interaction_cap=None, attestation=True,
        audit_trail=True, reggeoint=False, open_source=False,
        who="AI companies + games embedding MEOK via CONNECT at scale",
        notes="Pay per interaction. The platform runs its own LLM; pays MEOK for "
              "character+memory+safety. This is where big AI cos eat alongside us."),
    "enterprise": Tier(
        id="enterprise", label="Enterprise", price_gbp_month=1499.0,
        per_interaction_gbp=None, hosting="meok", characters="all+custom",
        memory_cross_platform=True, daily_interaction_cap=None, attestation=True,
        audit_trail=True, reggeoint=True, open_source=False,
        who="regulated enterprises, governments",
        notes="Everything + RegGeoInt compliance map + full audit trail + SLA. Contract/seat."),
}

# Which registry character-tiers a billing tier can hatch
_CHAR_ACCESS = {
    "free-only": {"free"},
    "all": {"free", "pro", "gaming"},
    "all+custom": {"free", "pro", "gaming"},  # + bespoke characters out of band
}


def get_tier(tier_id: str) -> Tier:
    t = TIERS.get(tier_id)
    if t is None:
        raise KeyError(f"unknown tier: {tier_id!r} (have {list(TIERS)})")
    return t


def can_hatch(tier_id: str, character_tier: str) -> bool:
    """Can a billing tier hatch a character of this registry tier?"""
    allowed = _CHAR_ACCESS.get(get_tier(tier_id).characters, {"free"})
    return character_tier in allowed


def quote(tier_id: str, interactions: int = 0) -> dict:
    """What a tier costs for a given monthly interaction volume. Honest math —
    no fabricated 'x 1B/day' fantasy; just this tier's real price."""
    t = get_tier(tier_id)
    monthly = t.price_gbp_month or 0.0
    usage = (t.per_interaction_gbp or 0.0) * interactions
    return {
        "tier": t.id, "label": t.label,
        "flat_gbp_month": monthly,
        "usage_gbp": round(usage, 2),
        "total_gbp_month": round(monthly + usage, 2),
        "interactions": interactions,
        "free": (monthly == 0.0 and (t.per_interaction_gbp or 0.0) == 0.0),
    }


def entitlements(tier_id: str) -> dict:
    """The feature set a tier unlocks — what CONNECT enforces."""
    t = get_tier(tier_id)
    return {
        "tier": t.id,
        "hosting": t.hosting,
        "characters": t.characters,
        "memory_cross_platform": t.memory_cross_platform,
        "daily_cap": t.daily_interaction_cap,
        "attestation": t.attestation,
        "audit_trail": t.audit_trail,
        "reggeoint": t.reggeoint,
        "open_source": t.open_source,
    }


def ladder() -> list:
    """The whole ladder, for a pricing page or a partner deck."""
    order = ["local", "free", "pro", "professional", "usage", "enterprise"]
    out = []
    for tid in order:
        t = TIERS[tid]
        price = ("£0 (self-host)" if t.id == "local"
                 else "£0" if (t.price_gbp_month or 0) == 0
                 else f"£{t.per_interaction_gbp}/interaction" if t.per_interaction_gbp
                 else f"£{t.price_gbp_month:.0f}/mo")
        out.append({"id": t.id, "label": t.label, "price": price, "who": t.who})
    return out


if __name__ == "__main__":
    import json
    print("=== MEOK ONE — the everyone-eats ladder ===\n")
    for row in ladder():
        print(f"  {row['label']:24} {row['price']:22} → {row['who']}")
    print("\n--- example quote: a game doing 500k interactions/mo on USAGE ---")
    print(json.dumps(quote("usage", 500_000), indent=2))
    print("\n--- local tier entitlements (free, self-host) ---")
    print(json.dumps(entitlements("local"), indent=2))
