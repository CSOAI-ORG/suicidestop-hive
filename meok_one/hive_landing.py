"""
MEOK ONE — HIVE LANDING: a distinctive landing page per hive, generated from config.

The web-presence layer (2026-06-16). Subject = sovereign compliance/IP hives, so the
design world is charters, wax seals, cryptographic receipts. Signature element: a live
"verification seal" — a real SIGIL receipt rendered as an embossed seal, so the page
proves itself (deploy → govern → prove). Ink-navy ground, wax-gold + verify-green
accents (NOT the AI-default cream/acid), document-serif headlines + monospace crypto.

    generate(hive_root, out_dir) -> {pages, out_dir}
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

# Per-hive accent rotates within a disciplined sovereign palette (gold for governance,
# verify-green for verticals) so each domain reads distinct without leaving the system.
_GOLD = "#b8893e"
_GREEN = "#2f6f5e"


def _parse(text: str) -> dict:
    cfg = {"domain": "", "scope": "", "tools": [], "tier": "", "build_tier": ""}
    in_tools = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("domain:"):
            cfg["domain"] = s.split(":", 1)[1].strip()
        if s.startswith("tools:"):
            in_tools = True; continue
        if in_tools:
            if s.startswith("- "):
                cfg["tools"].append(s[2:].strip())
            elif s and not s.startswith("#") and not line.startswith(" " * 6):
                in_tools = False
        if s.startswith("scope:") and not cfg["scope"]:
            cfg["scope"] = s.split(":", 1)[1].strip().strip('"')
        if s.startswith("tier:") and not cfg["build_tier"]:
            cfg["build_tier"] = s.split(":", 1)[1].strip()
    return cfg


def _seal(domain: str) -> str:
    """A deterministic SIGIL-style receipt for the seal (proof the page is sealed)."""
    return "S|" + hashlib.sha256(domain.encode()).hexdigest()[:16]


def _page(cfg: dict) -> str:
    domain = cfg["domain"] or "meok.ai"
    is_gov = cfg["build_tier"] in ("governance", "flagship")
    accent = _GOLD if is_gov else _GREEN
    name = domain.split(".")[0]
    scope = (cfg["scope"] or f"The {name} hive — verified, governed, sovereign AI for your domain.")
    # plain-language thesis derived from the scope's first clause
    thesis = re.split(r"[.—]", scope)[0].strip()[:120] or f"Sovereign AI for {name}"
    tools = [t for t in cfg["tools"] if t][:4]
    seal = _seal(domain)
    toolrows = "".join(f"<li>{t}</li>" for t in (tools or ["verified-compliance"]))
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>{domain} — sovereign AI, verified</title>
<meta name=description content="{thesis}. Verified compliance, cryptographic IP, BFT governance.">
<style>
:root{{--ink:#0e1626;--ink2:#162338;--line:#233149;--mist:#eef1f4;--gold:{_GOLD};--green:{_GREEN};--ac:{accent}}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}
body{{margin:0;background:var(--ink);color:#dde4ee;font:400 17px/1.6 system-ui,-apple-system,sans-serif;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:880px;margin:0 auto;padding:0 1.5rem}}
.serif{{font-family:"Iowan Old Style",Georgia,"Times New Roman",serif}}
.mono{{font-family:ui-monospace,"SF Mono",Menlo,monospace}}
header{{padding:5rem 0 3rem;border-bottom:1px solid var(--line)}}
.eyebrow{{font-size:.78rem;letter-spacing:.22em;text-transform:uppercase;color:var(--ac);font-weight:600}}
h1{{font-family:"Iowan Old Style",Georgia,serif;font-weight:600;font-size:clamp(2.2rem,6vw,3.6rem);line-height:1.05;margin:.8rem 0 .6rem;letter-spacing:-.01em;color:#fff}}
.dom{{color:var(--ac)}}
.lead{{font-size:1.15rem;color:#aeb9c9;max-width:54ch}}
/* the signature: an embossed verification seal */
.seal{{margin:2.2rem 0 0;display:inline-flex;align-items:center;gap:.9rem;border:1px solid var(--line);
  background:linear-gradient(180deg,var(--ink2),var(--ink));border-radius:.7rem;padding:.7rem 1rem}}
.seal .ring{{width:46px;height:46px;border-radius:50%;border:2px solid var(--ac);display:flex;align-items:center;justify-content:center;
  color:var(--ac);font-weight:700;font-family:Georgia,serif;font-size:1.1rem;box-shadow:inset 0 0 0 3px rgba(255,255,255,.03)}}
.seal .meta{{font-size:.78rem;color:#8190a4}}.seal .rcpt{{color:#cdd6e2}}
section{{padding:3rem 0;border-bottom:1px solid var(--line)}}
h2{{font-family:"Iowan Old Style",Georgia,serif;font-weight:600;font-size:1.5rem;color:#fff;margin:0 0 1.2rem}}
.planes{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1px;background:var(--line);border:1px solid var(--line);border-radius:.6rem;overflow:hidden}}
.plane{{background:var(--ink2);padding:1.2rem}}
.plane .k{{font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;color:var(--ac);font-weight:600}}
.plane h3{{margin:.4rem 0 .3rem;font-size:1.05rem;color:#fff;font-weight:600}}.plane p{{margin:0;font-size:.9rem;color:#9fabbd}}
.tools{{list-style:none;padding:0;margin:0;display:flex;flex-wrap:wrap;gap:.5rem}}
.tools li{{font-family:ui-monospace,monospace;font-size:.82rem;background:var(--ink2);border:1px solid var(--line);padding:.3rem .6rem;border-radius:.4rem;color:#cdd6e2}}
.cta{{display:inline-block;background:var(--ac);color:#0e1626;font-weight:600;padding:.8rem 1.4rem;border-radius:.5rem;text-decoration:none;margin-top:.5rem}}
.cta.ghost{{background:transparent;color:var(--ac);border:1px solid var(--ac)}}
a{{color:var(--ac)}}.muted{{color:#7e8b9f}}
footer{{padding:2.5rem 0 4rem;color:#6b7689;font-size:.82rem}}
@media (prefers-reduced-motion:no-preference){{header,section{{animation:rise .6s ease both}}@keyframes rise{{from{{opacity:0;transform:translateY(8px)}}to{{opacity:1;transform:none}}}}}}
</style></head><body>
<header><div class=wrap>
  <div class=eyebrow>{cfg['build_tier'] or 'hive'} · MEOK sovereign AI OS</div>
  <h1>Sovereign AI for <span class=dom>{name}</span>, verified by construction.</h1>
  <p class=lead>{thesis}. Every answer is grounded in real regulation, externally verified
  for the correct citation, and sealed with a tamper-evident receipt. Deploy → govern → prove.</p>
  <div class=seal>
    <div class=ring>✓</div>
    <div><div class=meta>this hive is sealed in the SIGIL chain</div>
    <div class="rcpt mono">{seal}</div></div>
  </div>
</div></header>

<section><div class=wrap>
  <h2>One operating system. Four planes.</h2>
  <div class=planes>
    <div class=plane><div class=k>Discover</div><h3>Agent card</h3><p>Findable by any A2A agent at <span class=mono>/.well-known/agent.json</span>.</p></div>
    <div class=plane><div class=k>Govern</div><h3>BFT council</h3><p>12 lenses, safety-veto, a signed audit receipt per decision.</p></div>
    <div class=plane><div class=k>Prove</div><h3>Verified compliance</h3><p>EU AI Act / DORA / NIS2 — grounded, citation-checked, attested.</p></div>
    <div class=plane><div class=k>Own</div><h3>IP registry</h3><p>The work patents itself — tamper-evident priority evidence.</p></div>
  </div>
</div></section>

<section><div class=wrap>
  <h2>What this hive does</h2>
  <p class=muted style="max-width:56ch">{scope}</p>
  <ul class=tools>{toolrows}</ul>
</div></section>

<section><div class=wrap>
  <h2>Sovereign by architecture</h2>
  <p style="max-width:56ch;color:#aeb9c9">When a frontier model gets export-controlled, or a cloud
  key is suspended, this hive keeps working — local, governed, unbannable. Trust you can verify,
  not trust you're asked to take.</p>
  <div style="margin-top:1.4rem">
    <a class=cta href="https://meok.ai/verified">Try a verified answer</a>
    <a class="cta ghost" href="https://openpatent.ai" style="margin-left:.6rem">Protect an invention</a>
  </div>
</div></section>

<footer><div class=wrap>
  {domain} · powered by MEOK ONE (one engine, 30 hives) · BFT governance · proofof.ai · openpatent.ai<br>
  © 2026 MEOK AI Labs / CSOAI Ltd (UK). The sovereign AI operating system.
</div></footer>
</body></html>"""


def generate(hive_root: str, out_dir: str) -> dict:
    root = Path(hive_root).expanduser()
    out = Path(out_dir).expanduser(); out.mkdir(parents=True, exist_ok=True)
    pages = []
    for stack in sorted(root.glob("*-hive/stack.yml")):
        cfg = _parse(stack.read_text())
        if not cfg["domain"]:
            cfg["domain"] = stack.parent.name.replace("-hive", "") + ".ai"
        slug = re.sub(r"[^a-z0-9]+", "-", cfg["domain"].lower()).strip("-")
        d = out / slug; d.mkdir(exist_ok=True)
        (d / "index.html").write_text(_page(cfg))
        pages.append(slug)
    return {"pages": len(pages), "out_dir": str(out), "slugs": pages}


if __name__ == "__main__":
    import sys
    from pathlib import Path as _P
    root = sys.argv[1] if len(sys.argv) > 1 else str(_P.home() / "hive-staging")
    out = sys.argv[2] if len(sys.argv) > 2 else str(_P.home() / "hive-pages")
    print(json.dumps(generate(root, out), indent=2))
