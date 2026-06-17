# MEOK ONE as the OS — how every inner product runs on it (grounded)

*Answering: "MEOK ONE must work seamlessly e2e with all inner products — sigil, gaming,
characters, council, dome, everything — one improved Step-3.5 UX with our character, across
all platforms, all protocols (A2A/ABCI/ACP/libp2p/attestation), EAT all."*

Written 2026-05-30. **Marked by what's REAL code vs doc-only, so the integration layer is
honest, not a diagram.** Verified against the live SOV3 MCP (110 tools) + the repo.

---

## The shape: MEOK ONE is the spine, inner products are organs that plug into it

```
                    ┌──────────────────────────────────────┐
   END USER  ─────► │  MEOK ONE  (the character + the OS UX) │  ◄── any platform:
   (ChatGPT/Claude/ │  registry · brain · hatch · memory ·   │      web · TUI · opencode ·
    game · TUI)     │  tiers · router · connect (the rail)   │      Amica 3D · games · SaaS
                    └───────────────┬──────────────────────-─┘
                                    │ connect() = neutral rail (ingredients, not replies)
        ┌───────────────┬──────────┼───────────┬───────────────┬──────────────┐
        ▼               ▼          ▼            ▼               ▼              ▼
   characters       council      gaming       memory       attestation     protocols
   (27, ✅ real)   (✅ 2 live)  (✅ 11 live)  (✅ 6 live)   (✅ live)       (✅ shipped MCPs)
   registry.py    submit/vote   guardian_*   record/query  proofof.ai      a2a/abci/acp/libp2p
```

## What's REAL (verified 2026-05-30) — these can plug in today

| Inner product | Status | Where / how MEOK ONE reaches it |
|---|---|---|
| **MEOK Characters** | ✅ 27, built + tested | `meok_one/registry.py` — the canonical source; brain.py makes them talk |
| **MEOK Council** | ✅ 2 tools LIVE on SOV3 | `submit_council_proposal`, `vote_on_proposal` — router/connect can call via MCP |
| **MEOK Gaming** | ✅ 11 `guardian_*` tools LIVE | `guardian_moderate_chat`, `guardian_check_game_content` etc. — already wired into connect.py's game age-gates |
| **MEOK Memory** | ✅ 6 tools LIVE | `record_memory`/`query_memories` — memory.py wraps them cross-platform |
| **MEOK Sigil** | ✅ real package | `meok-sigil/` (has egg-info, installed) — needs a connect() adapter |
| **Attestation** | ✅ LIVE | `proofof.ai/verify/<cert_id>` — the GDPR-proof layer |
| **Model router** | ✅ built today | `router.py` — switch any LLM, tier-gated |
| **Protocols** | ✅ shipped as MCPs | `a2a-governance-bridge-mcp`, `meok-abci-bridge-mcp`, `meok-stripe-acp-checkout-mcp`, `meok-libp2p-agent-mesh-mcp`, `agent-handoff-certified-mcp`, `agent-policy-enforcement-mcp` |

## What's DOC-ONLY (vision, not yet code) — be honest in any pitch

| Named thing | Reality |
|---|---|
| **MEOK Dome** | Appears only in strategy docs (`ralph_mode_30day.py` mention) — no product code. Concept, not built. |
| **MEOK Gaming as a *product*** | The *safety tools* are live (guardian_*), but there's no standalone "MEOK Gaming" app/SDK yet — it's the guardian layer + Pixel character, not a shipped game platform. |
| **"all platforms" (Unity/Unreal/Roblox plugins)** | Not built. connect.py is the rail they'd call, but no engine plugins exist. |
| **"EAT all" revenue at scale** | The tiers + Stripe links are real (Pro £9, Ent £1,499 live); the £-numbers in the big strategy docs are projections, not bookings. |

## The integration contract (how a NEW inner product joins the OS)

Every inner product becomes "on MEOK ONE" by exposing **one of two shapes** that connect.py
already speaks:

1. **As an MCP tool** (like council/gaming/memory) → the router calls it by name. Zero new
   glue: if it's a tool on SOV3 :3101 or a shipped MCP, MEOK ONE can already invoke it.
2. **As a connect() consumer** (like a game/SaaS) → it calls `connect(character, user, msg,
   tier)`, gets `{system_prompt, memory_context, safety_policy, billing}`, runs its own model
   (or uses `router.ask`), then `remember()`s the exchange. Two calls.

That contract is the "seamless e2e" — not a monolith, but **one rail + one tool convention**
every organ already fits. New products don't integrate *into* MEOK ONE; they *speak its two
verbs*.

## Honest next steps to make "everything on MEOK ONE" literally true

1. **Sigil adapter** — wrap `meok-sigil` as either an MCP tool or a connect() consumer (small).
2. **A `products.py` registry** in MEOK ONE — one list of inner products + how each connects
   (MCP tool name vs connect-consumer), so the OS can enumerate what's plugged in. (Buildable now.)
3. **Council/gaming convenience wrappers** in MEOK ONE (like memory.py wraps memory) so a
   character can call `council.propose(...)` / `gaming.check(...)` without raw MCP.
4. **The actual UX shell** (the "improved Step-3.5 with our character") — that's the Amica 3D
   frontend wired to registry+brain+router. The biggest remaining build; needs the frontend.

## Bottom line
The **spine is real and tested** (62/62 tests, 7 modules). **5 of the named inner products are
real and reachable today** (characters, council, gaming-safety, memory, attestation) + all the
protocol MCPs ship. **Dome + game-engine plugins + the 3D UX shell are not built.** "Everything
on MEOK ONE" is ~60% real substrate + a clear 4-step path for the rest — and it does NOT require
inflating what exists to be a strong story.

---
© CSOAI LTD (trading as MEOK AI Labs) · internal · grounded integration map
