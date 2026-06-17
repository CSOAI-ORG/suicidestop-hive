# MEOK ONE — live Stripe links (single source of truth)

Created 2026-05-30 via Stripe MCP (account: **MEOK AI LTD**, live mode). These are the
real, chargeable links — wire them into the pricing page / tiers.py when ready.

| Tier | Price | Stripe product | Stripe price | Payment link |
|---|---|---|---|---|
| **Local** | £0 (self-host, OSS) | — | — | no product — free, runs on user's machine |
| **Free** | £0 (hosted) | — | — | no product — free on-ramp |
| **Pro** | £9 / mo | `prod_Ubx9DdgoXPnzUD` | `price_1TcjHUQvIueK5Xpb1tLUecD3` | https://buy.stripe.com/8x2dRb94obIK8sl1Uc8k916 |
<!-- Pro price verified £9 (unit_amount 900) via search_stripe_resources 2026-05-30. A fetch_stripe_resources read briefly returned 149900 — that was a flaky tool read, NOT the real price. Confirmed 900. -->
<!-- Enterprise price/link verified REAL via create returns: price_1TcjU1QvIueK5XpbDoMa0d8M (149900), link plink_1TcjUuQvIueK5XpbmmG4v6G8. Earlier doc had fabricated IDs — corrected. -->
<!-- NOTE: buy.stripe.com returns HTTP 200 for ANY path (client-side SPA) — curl 200 does NOT prove a link is real. Only trust IDs/URLs returned directly by the Stripe create API. -->

| **Usage** | £0.002 / interaction | ⚠️ NOT created | — | sub-penny — needs a **metered** price with `unit_amount_decimal` set in the Stripe dashboard (the API create_price tool can't do sub-1p amounts). For platform/B2B deals, not self-serve. |
| **Enterprise** | £1,499 / mo | `prod_UbxMotixQGr9CN` | `price_1TcjU1QvIueK5XpbDoMa0d8M` | https://buy.stripe.com/7sY5kF3K4cMObEx2Yg8k917 |

## Notes
- **Local + Free are genuinely £0** — deliberately no Stripe product (creating £0 products
  would just add to the 100+ stale-product cleanup already on the list).
- **Usage tier is the one gap:** £0.002/interaction is below Stripe's 1p minimum for a
  standard price. It must be a metered price (`unit_amount_decimal: "0.2"`, per-unit, metered
  usage) created in the dashboard — appropriate anyway since platforms sign contracts, not
  click a self-serve link.
- **Enterprise:** there is also a separate **CSOAI Enterprise £1,499** product from earlier
  (task #7). This `MEOK ONE Enterprise` is the consumer-product-branded top tier. If you'd
  rather not run two £1,499 products, archive one — flag which.

## To wire into the pricing surface
Drop the Pro + Enterprise links onto the MEOK ONE / pricing page. (Deferred from this session:
the live editor was returning corrupted file reads, so source edits to `tiers.py` / `README.md`
were held back rather than risk clobbering working code — do them when the environment is stable.)
