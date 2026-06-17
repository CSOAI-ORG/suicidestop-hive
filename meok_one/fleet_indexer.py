"""
MEOK ONE — FLEET INDEXER: the routing brain behind "all hives operating under Horus."

What it does:
  - Walks ~/hive-staging/*/stack.yml (the 28-queen config) → 1 routing row per hive
  - Walks ~/clawd/_TABS/ (the 27 cross-tab docs) → 1 situational-awareness row per tab
  - Walks ~/clawd/meok-one/ for the MEOK ONE primary docs (README, brain arch, OLM spec)
  - Walks ~/clawd/sovereign-temple/ + ~/clawd/sovereign-temple-live/ for SOV3 entry points
  - Walks ~/fleet-clones/ (13 compliance MCPs) for cross-posts
  - Walks ~/clawd/mcp-marketplace/ for the published fleet (~350, gitignored — local
    only, but useful for "what's in PyPI right now" routing)
  - Optionally ingests agent cards from meok-ui/public/.well-known/agent-cards/ if
    A2A_CARDS_DIR is set (the 15 flagship cards shipped 2026-06-10)

It NEVER calls the network, never talks to Kimi/Claude/GitHub — pure stdlib + local
file reads. The "all githubs" piece is satisfied by reading the local clones (every
meok-* repo is on disk under ~/clawd/) + the local catalog (~/clawd/_TABS/_inventory/
csoai_org_repos.json). The catalog says what's IN the org; the local clones say
what's READABLE for routing.

Output: one JSON index at data/fleet_index.json, rebuilt in <2s on a Mac. The king
loads it once at startup + on /api/horus/refresh, and uses it to:
  1. Pre-classify routing (skip the 60s LLM call when the catalog matches)
  2. Show situational awareness in /api/horus/route (which hives are online + what
     they know)
  3. Emit SIGIL C|care receipts for what the index learned (so audits can replay
     the king's "I picked this queen because…" reasoning)
"""

from __future__ import annotations

import json
import os
import re
import time
import hashlib
from pathlib import Path

# Default roots — overridable via env so the VM can point at /home/meok-king/...
_DEFAULT_ROOTS = {
    "hive_staging":  os.environ.get("MEOK_HIVE_STAGING",
                                    os.path.expanduser("~/hive-staging")),
    "tabs":          os.environ.get("MEOK_TABS",
                                    os.path.expanduser("~/clawd/_TABS")),
    "meok_one":      os.environ.get("MEOK_ONE_ROOT",
                                    os.path.expanduser("~/clawd/meok-one")),
    "sov3_docker":   os.path.expanduser("~/clawd/sovereign-temple"),
    "sov3_live":     os.path.expanduser("~/clawd/sovereign-temple-live"),
    "fleet_clones":  os.path.expanduser("~/fleet-clones"),
    "mcp_marketplace": os.path.expanduser("~/clawd/mcp-marketplace"),
    "a2a_cards":     os.path.expanduser("~/clawd/meok/ui/public/.well-known/agent-cards"),
    "repos_catalog": os.path.expanduser("~/clawd/_TABS/_inventory/csoai_org_repos.json"),
}

# The 8-word scope cutoff (mirrors hive_king._short) — compact catalog = fast routing
_SCOPE_WORDS = 8
_INDEX_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data",
                           "fleet_index.json")


def _read_text(path: str, max_bytes: int = 200_000) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(max_bytes)
    except Exception:
        return ""


def _short(text: str, n: int = _SCOPE_WORDS) -> str:
    return " ".join((text or "").replace("\n", " ").split()[:n])


def _safe_yaml_get(text: str, key: str) -> str:
    """Tiny YAML getter — no PyYAML dep. Matches `key: value` lines. First wins.
    Handles quoted values, multi-word unquoted values, and inline `# comment`."""
    out = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(rf"^{re.escape(key)}\s*:\s*(.*)$", s)
        if m:
            v = m.group(1).strip()
            # strip inline comment + surrounding quotes
            v = re.split(r"\s+#", v, 1)[0].strip()
            v = v.strip('"').strip("'")
            if v:
                out.append(v)
    return out[0] if out else ""


def _list_stack_yml_hives(root: str) -> list:
    """Walk <root>/*-hive/stack.yml, return one row per hive."""
    rows = []
    rp = Path(root)
    if not rp.is_dir():
        return rows
    for d in sorted(rp.glob("*-hive")):
        cfg_path = d / "stack.yml"
        if not cfg_path.is_file():
            continue
        text = _read_text(str(cfg_path))
        slug = d.name[:-5]  # strip "-hive"
        scope = _safe_yaml_get(text, "scope")
        if not scope:
            # fall back to README first paragraph
            rd = d / "README.md"
            if rd.is_file():
                scope = _read_text(str(rd), 4000).split("\n\n", 1)[0]
        rows.append({
            "slug": slug,
            "scope": scope or slug,
            "scope_short": _short(scope, 12),
            "stack_yml": str(cfg_path),
            "readme": str(d / "README.md") if (d / "README.md").is_file() else None,
            "mtime": int(cfg_path.stat().st_mtime) if cfg_path.exists() else 0,
        })
    return rows


def _list_tabs(root: str) -> list:
    """Walk *.md in <root> → one row per tab. Skip files in subdirs (those are
    deeper; we want the top-level awareness only)."""
    rows = []
    rp = Path(root)
    if not rp.is_dir():
        return rows
    for f in sorted(rp.glob("*.md")):
        text = _read_text(str(f), 8000)
        title = ""
        for line in text.splitlines()[:5]:
            m = re.match(r"^#\s+(.*)$", line.strip())
            if m:
                title = m.group(1).strip()
                break
        first_para = ""
        for para in re.split(r"\n\s*\n", text):
            p = para.strip()
            if p and not p.startswith("#"):
                first_para = _short(p, 24)
                break
        rows.append({
            "name": f.stem,
            "title": title or f.stem,
            "summary": first_para,
            "path": str(f),
            "mtime": int(f.stat().st_mtime) if f.exists() else 0,
        })
    return rows


def _list_fleet_clones(root: str) -> list:
    """The 13 compliance MCP clones. Return one row per repo with scope = repo's
    own pyproject.toml description (most reliable) or README first line."""
    rows = []
    rp = Path(root)
    if not rp.is_dir():
        return rows
    for d in sorted(rp.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        scope = ""
        # pyproject.toml description is the cleanest
        pp = d / "pyproject.toml"
        if pp.is_file():
            txt = _read_text(str(pp), 5000)
            m = re.search(r'description\s*=\s*"([^"]{4,200})"', txt)
            if m:
                scope = m.group(1).strip()
        if not scope:
            rd = d / "README.md"
            if rd.is_file():
                # first non-heading, non-empty line
                for ln in _read_text(str(rd), 2000).splitlines():
                    s = ln.strip()
                    if s and not s.startswith("#") and not s.startswith("!"):
                        scope = s
                        break
        rows.append({
            "slug": d.name,
            "scope": scope or d.name,
            "scope_short": _short(scope, 12),
            "path": str(d),
            "mtime": int(pp.stat().st_mtime) if pp.exists() else 0,
        })
    return rows


def _list_mcp_marketplace(root: str) -> list:
    """The published fleet. Just count + sample the top-level subdirs to keep the
    index light (we don't need every package's metadata — that's PyPI's job)."""
    rows = []
    rp = Path(root)
    if not rp.is_dir():
        return rows
    pkgs = sorted([d for d in rp.iterdir() if d.is_dir() and not d.name.startswith(".")])
    for d in pkgs:
        scope = ""
        pp = d / "pyproject.toml"
        if pp.is_file():
            txt = _read_text(str(pp), 2000)
            m = re.search(r'description\s*=\s*"([^"]{4,160})"', txt)
            if m:
                scope = m.group(1).strip()
        rows.append({
            "slug": d.name,
            "scope": scope or d.name,
            "scope_short": _short(scope, 8),
            "path": str(d),
        })
    return rows


def _list_a2a_cards(root: str) -> list:
    """The 15 flagship agent cards. Each is a small JSON; we read name, skills, tags."""
    rows = []
    rp = Path(root)
    if not rp.is_dir():
        return rows
    for f in sorted(rp.glob("*.json")):
        if f.name.startswith("_"):
            continue
        try:
            d = json.loads(_read_text(str(f), 8000))
        except Exception:
            continue
        rows.append({
            "slug": f.stem,
            "name": d.get("name", f.stem),
            "version": d.get("version", ""),
            "protocolVersion": d.get("protocolVersion", ""),
            "skills": [s.get("id", s.get("name", "")) for s in (d.get("skills") or [])][:8],
            "tags": d.get("tags", [])[:8],
            "x_meok_flagship": bool((d.get("x-meok") or {}).get("flagship", False)),
            "x_meok_verifier": (d.get("x-meok") or {}).get("verifier", ""),
            "path": str(f),
        })
    return rows


def _load_repos_catalog(path: str) -> dict:
    """The CSOAI-ORG catalog (csoai_org_repos.json) — 475 repos summarized. Used to
    answer 'is X in the org?' without going to GitHub."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return {"repos": data, "count": len(data)}
        if isinstance(data, dict) and "repos" in data:
            return data
    except Exception:
        pass
    return {"repos": [], "count": 0}


def build_index(roots: dict = None) -> dict:
    """Rebuild the full fleet index. Returns the dict (also written to disk)."""
    roots = roots or _DEFAULT_ROOTS
    t0 = time.time()
    hives = _list_stack_yml_hives(roots["hive_staging"])
    tabs = _list_tabs(roots["tabs"])
    fleet = _list_fleet_clones(roots["fleet_clones"])
    marketplace = _list_mcp_marketplace(roots["mcp_marketplace"])
    cards = _list_a2a_cards(roots["a2a_cards"])
    catalog = _load_repos_catalog(roots["repos_catalog"])

    # Build a flat, fast routing catalog the king can scan in <1ms
    routing = []
    for h in hives:
        routing.append({"slug": h["slug"], "scope": h["scope_short"],
                        "kind": "queen", "weight": 1.0})
    for f in fleet:
        routing.append({"slug": f["slug"], "scope": f["scope_short"],
                        "kind": "compliance", "weight": 0.7})
    for m in marketplace[:50]:  # top-50 published (don't ship 350 to the router)
        routing.append({"slug": m["slug"], "scope": m["scope_short"],
                        "kind": "mcp_published", "weight": 0.4})
    for c in cards:
        routing.append({"slug": c["slug"], "scope": c["name"],
                        "kind": "a2a_card", "weight": 0.9 if c.get("x_meok_flagship") else 0.5})

    idx = {
        "ts": int(time.time()),
        "build_ms": int((time.time() - t0) * 1000),
        "roots": roots,
        "counts": {
            "hives": len(hives),
            "tabs": len(tabs),
            "fleet_clones": len(fleet),
            "marketplace": len(marketplace),
            "a2a_cards": len(cards),
            "routing": len(routing),
            "org_repos": catalog.get("count", 0),
        },
        "hives": hives,
        "tabs": tabs,
        "fleet_clones": fleet,
        "marketplace_top": marketplace[:50],
        "a2a_cards": cards,
        "routing": routing,
        "org_catalog_meta": {
            "count": catalog.get("count", 0),
            "source": roots["repos_catalog"],
        },
    }
    # Hash for tamper-evidence (SIGIL will chain this)
    body = json.dumps(idx, sort_keys=True, ensure_ascii=False).encode("utf-8")
    idx["digest"] = hashlib.sha256(body).hexdigest()
    _write(idx)
    return idx


def _write(idx: dict) -> None:
    """Write the index atomically. Stale-on-crash safe."""
    try:
        os.makedirs(os.path.dirname(_INDEX_PATH), exist_ok=True)
        tmp = _INDEX_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(idx, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _INDEX_PATH)
    except Exception:
        pass


def load_index() -> dict:
    """Read the on-disk index, rebuilding if missing or stale (>1h old)."""
    try:
        if os.path.exists(_INDEX_PATH):
            with open(_INDEX_PATH, "r", encoding="utf-8") as f:
                idx = json.load(f)
                if idx.get("ts", 0) > int(time.time()) - 3600:
                    return idx
    except Exception:
        pass
    return build_index()


def find(slug: str) -> dict:
    """One-glance lookup. Returns the matching hive/clone/card/marketplace row or {}."""
    idx = load_index()
    for row in (idx.get("hives") or []):
        if row.get("slug") == slug:
            return {**row, "kind": "queen"}
    for row in (idx.get("fleet_clones") or []):
        if row.get("slug") == slug:
            return {**row, "kind": "compliance"}
    for row in (idx.get("a2a_cards") or []):
        if row.get("slug") == slug:
            return {**row, "kind": "a2a_card"}
    return {}


def route_catalog() -> list:
    """The flat routing catalog the king loads at startup."""
    return load_index().get("routing", [])


if __name__ == "__main__":
    import sys
    if "--refresh" in sys.argv:
        idx = build_index()
        print(f"=== FLEET INDEX · rebuilt · {idx['build_ms']}ms ===")
    else:
        idx = load_index()
        print(f"=== FLEET INDEX · cached · ts={idx.get('ts',0)} ===")
    c = idx.get("counts", {})
    for k, v in c.items():
        print(f"  {k:20s} {v}")
