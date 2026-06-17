# 🐝 Operating the Hive — one page

Two things are called "hive". This page covers both and how an operator drives them.

## 1. The BRAIN — King → Queens → Honeycomb (this repo, meok-one)

```
👤 you ──▶ 🤴 KING (SOV3 sovereign, thin stateless router)
                 │ "which hive(s) answer this?"
        ┌────────┼──────── …×28
        ▼        ▼        ▼
     👑 queen  👑 queen  👑 queen   = one meok-one engine per hive (MoE + BFT)
        └────────┴── all deposit honey ──▶ 🍯 HONEYCOMB (SOV3 memory)
```

A queen is NOT a new stack — it's THIS engine parameterised by a hive's `stack.yml`. 28 queens = 28 configs on 1 battle-tested engine.

**Operate it (now packaged as console commands):**
```bash
pip install -e .            # registers the commands below
meok-king "I need to tip soil at a construction site — what permits?"   # route → answer
meok-king "<msg>" --fan     # fan out to multiple queens + convene a council, synthesize
meok-queen construction "<msg>" [council|fast]   # talk to one hive's queen directly
python -m tools.m3_tui      # interactive TUI chat (M3); /audit <x>, /reset, /quit
```
- King routing is thin + stateless so a SOV3 memory/VM wobble can't stop it picking a queen.
- Inference runs on the GCP VM (fast box); SOV3 king/honeycomb run on the Mac `:3101`.

## 2. The FUNNEL SITES — `.ai` conversion hive (clawd workspace)

ONE master generator, do not fork. See `~/clawd/HIVE_MASTER.md`.
```bash
cd ~/clawd && python3 build_hive_conversion_pages.py     # generates 18 <slug>-deploy/ sites
cd <slug>-deploy && vercel deploy --prod --yes           # deploy one
```
Each site = index + pricing + signup + partner + enterprise + industry/* + interactive MCP demo + llms.txt + sitemap + robots.

## Operator workflow (us → SOV3 → queens → end users)
1. **End user / agent** asks the KING (one mouth) or lands on a funnel site.
2. **King** routes to the right queen(s); funnel sites surface the matching MCP demo.
3. **Queens** answer with MoE + BFT (12-lens council, safety-veto + vote), scoped to that hive's MCPs.
4. **Honeycomb** (SOV3 memory) gathers what every hive learns.
5. **Us** edit one place each: a queen = its `stack.yml`; a funnel site = its `hive_extra_*.py` entry.

## Don't re-fork
Claim hive work in the SOV3 coord hub + acquire file locks first — multiple agents (jeeves, WAVE, Mavis) touch this surface. See memory `project_hive_conversion_pages`.
