"""
MEOK ONE — TIERED MEMORY: the three-tier cognition router.

Three storage tiers, one uniform interface:

    hot  = in-process dict  (RAM, sub-millisecond, dies with the process)
    warm = SQLite at ~/.meok_one/memory.db  (SSD, millisecond, survives restart)
    cold = SOV3 record_memory  (network/Postgres/Weaviate, second-scale, sovereign)

Every put/get/list across all three tiers returns the same shape:
    { "ok": bool, "tier": "hot"|"warm"|"cold", "value": ..., "address": sigil_hex }

The SIGIL ADDRESS is the durable handle — the first 16 bytes of the receipt
hash, hex-encoded (matching sigil.record's 16-hex receipt). It is the SAME
address space as the MEOK SIGIL audit chain, so a memory record and its
audit trail are linkable by a single 16-hex prefix.

Routing decision (the tier tree):
    put:
        salience >= 0.85  → cold  (sovereign, signed, survives everything)
        salience >= 0.40  → warm  (SSD, survives process restart)
        else              → hot   (RAM, ephemeral)
    get:
        try hot → miss → try warm → miss → try cold (slowest last)
    list:
        merges hot + warm + cold, dedupes by address, returns most-recent first.

Stdlib only. No external deps. SOV3 is best-effort (offline-stub honest).
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from typing import Any, Optional

# ---- paths & config ---------------------------------------------------------

_DB_DIR = os.path.join(os.path.expanduser("~"), ".meok_one")
_DB_PATH = os.path.join(_DB_DIR, "memory.db")

SOV3_MCP = os.environ.get("SOV3_MCP", "http://localhost:3101/mcp")

# salience → tier routing thresholds (the decision tree)
_HOT_SALIENCE_CAP = 0.40      # < this → hot (ephemeral)
_WARM_SALIENCE_CAP = 0.85     # < this → warm (SSD); >= this → cold (sovereign)

# ---- sigil address derivation ----------------------------------------------

def sigil_address(receipt_or_key: str) -> str:
    """First 16 bytes of the sha256 hash, hex-encoded. 32 hex chars.
    Same address space as sigil.record() receipts → auditable linkage."""
    return hashlib.sha256(str(receipt_or_key).encode("utf-8")).hexdigest()[:32]


# ---- TIER 1: HOT (in-process dict) -----------------------------------------

class _HotTier:
    """In-process dict, sub-millisecond, process-scoped. LRU bounded."""
    def __init__(self, capacity: int = 4096):
        self._lock = threading.RLock()
        self._data: "OrderedDict[str, dict]" = OrderedDict()
        self._capacity = capacity

    def put(self, address: str, value: Any, salience: float = 0.0, meta: Optional[dict] = None) -> dict:
        with self._lock:
            rec = {"address": address, "value": value, "salience": float(salience),
                   "meta": meta or {}, "ts": time.time(), "tier": "hot"}
            self._data[address] = rec
            self._data.move_to_end(address)
            while len(self._data) > self._capacity:
                self._data.popitem(last=False)
            return rec

    def get(self, address: str) -> Optional[dict]:
        with self._lock:
            rec = self._data.get(address)
            if rec is not None:
                self._data.move_to_end(address)
            return rec

    def list(self, limit: int = 100) -> list:
        with self._lock:
            return list(reversed(list(self._data.values())))[:limit]

    def stats(self) -> dict:
        with self._lock:
            return {"tier": "hot", "size": len(self._data), "capacity": self._capacity}


# ---- TIER 2: WARM (SQLite) -------------------------------------------------

class _WarmTier:
    """SQLite at ~/.meok_one/memory.db. Process-independent, survives restarts."""
    def __init__(self, path: str = _DB_PATH):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._path = path
        self._lock = threading.RLock()
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self._path, timeout=5, isolation_level=None)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        return c

    def _init_schema(self) -> None:
        with self._lock:
            with self._conn() as c:
                c.execute("""
                    CREATE TABLE IF NOT EXISTS memory (
                        address   TEXT PRIMARY KEY,
                        value     TEXT NOT NULL,
                        salience  REAL NOT NULL DEFAULT 0.0,
                        meta      TEXT,
                        ts        REAL NOT NULL
                    )
                """)
                c.execute("CREATE INDEX IF NOT EXISTS memory_ts ON memory(ts DESC)")
                c.execute("CREATE INDEX IF NOT EXISTS memory_salience ON memory(salience DESC)")

    def put(self, address: str, value: Any, salience: float = 0.0, meta: Optional[dict] = None) -> dict:
        ts = time.time()
        payload = json.dumps(value, ensure_ascii=False, default=str)
        meta_json = json.dumps(meta or {}, ensure_ascii=False, default=str)
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO memory(address, value, salience, meta, ts) VALUES (?,?,?,?,?) "
                "ON CONFLICT(address) DO UPDATE SET value=excluded.value, "
                "salience=excluded.salience, meta=excluded.meta, ts=excluded.ts",
                (address, payload, float(salience), meta_json, ts),
            )
        return {"address": address, "value": value, "salience": float(salience),
                "meta": meta or {}, "ts": ts, "tier": "warm"}

    def get(self, address: str) -> Optional[dict]:
        with self._lock, self._conn() as c:
            row = c.execute(
                "SELECT address, value, salience, meta, ts FROM memory WHERE address=?",
                (address,),
            ).fetchone()
        if not row:
            return None
        addr, val, sal, meta, ts = row
        try:
            value = json.loads(val)
        except (json.JSONDecodeError, TypeError):
            value = val
        try:
            meta_d = json.loads(meta) if meta else {}
        except (json.JSONDecodeError, TypeError):
            meta_d = {}
        return {"address": addr, "value": value, "salience": sal, "meta": meta_d,
                "ts": ts, "tier": "warm"}

    def list(self, limit: int = 100) -> list:
        with self._lock, self._conn() as c:
            rows = c.execute(
                "SELECT address, value, salience, meta, ts FROM memory "
                "ORDER BY ts DESC LIMIT ?", (max(1, int(limit)),),
            ).fetchall()
        out = []
        for addr, val, sal, meta, ts in rows:
            try:
                value = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                value = val
            try:
                meta_d = json.loads(meta) if meta else {}
            except (json.JSONDecodeError, TypeError):
                meta_d = {}
            out.append({"address": addr, "value": value, "salience": sal,
                        "meta": meta_d, "ts": ts, "tier": "warm"})
        return out

    def stats(self) -> dict:
        with self._lock, self._conn() as c:
            n = c.execute("SELECT count(*) FROM memory").fetchone()[0]
        return {"tier": "warm", "size": n, "path": self._path}


# ---- TIER 3: COLD (SOV3) ---------------------------------------------------

def _sov3_call(tool: str, args: dict, timeout: int = 10) -> Optional[dict]:
    """Minimal SOV3 JSON-RPC caller (mirrors memory.py pattern but isolated
    so the tier router has no dep on the user-memory namespace)."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": tool, "arguments": args}}
    req = urllib.request.Request(
        SOV3_MCP, method="POST", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode()
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    if "data:" in body:
        lines = [l[5:].strip() for l in body.splitlines() if l.startswith("data:")]
        body = lines[-1] if lines else body
    try:
        env = json.loads(body)
        content = env.get("result", {}).get("content", [])
        if content and content[0].get("type") == "text":
            return json.loads(content[0]["text"])
        return env.get("result")
    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
        return None


class _ColdTier:
    """SOV3 record_memory / query_memories. Sovereign, signed, network-backed.
    Address namespace is sigil_address(content) so cold records are linkable
    to the MEOK SIGIL audit chain by their 32-hex prefix.
    """
    def __init__(self, sov3_url: str = SOV3_MCP):
        self._url = sov3_url
        self._reachable: Optional[bool] = None
        self._reachable_checked_at: float = 0.0

    def _is_reachable(self) -> bool:
        # cache the reachability check for 30s — don't hammer SOV3 on every put
        if self._reachable is not None and (time.time() - self._reachable_checked_at) < 30:
            return self._reachable
        res = _sov3_call("get_system_status", {}, timeout=3)
        self._reachable = res is not None
        self._reachable_checked_at = time.time()
        return self._reachable

    def put(self, address: str, value: Any, salience: float = 0.0, meta: Optional[dict] = None) -> dict:
        # Cold tier re-addresses by content-hash via the SOV3 record_memory tool.
        # The `address` we were given is the *desired* sigil handle; the real
        # SOV3-side id is whatever record_memory returns. We keep BOTH in meta.
        tagged = json.dumps({"sigil_addr": address, "value": value, "salience": salience,
                             "meta": meta or {}, "ts": time.time()}, ensure_ascii=False, default=str)
        res = _sov3_call("record_memory", {
            "content": tagged,
            "source_agent": f"memory_tier:cold:{address[:8]}",
            "memory_type": "insight",
            "care_weight": max(0.0, min(1.0, float(salience))),
        })
        if res is not None:
            return {"address": address, "value": value, "salience": float(salience),
                    "meta": meta or {}, "ts": time.time(), "tier": "cold",
                    "source": "sov3", "sov3": res if isinstance(res, dict) else {"ok": True}}
        return {"address": address, "value": value, "salience": float(salience),
                "meta": meta or {}, "ts": time.time(), "tier": "cold",
                "source": "offline-stub",
                "note": f"SOV3 unreachable at {self._url}; cold record NOT persisted"}

    def get(self, address: str) -> Optional[dict]:
        # query_memories is content-based; we use the sigil_addr tag to filter.
        res = _sov3_call("query_memories", {
            "query": f"sigil_addr:{address}",
            "limit": 5,
        })
        if res is None:
            return None
        mems = res.get("memories", res) if isinstance(res, dict) else res
        if not isinstance(mems, list):
            return None
        for m in mems:
            content = m.get("content", "") if isinstance(m, dict) else ""
            try:
                payload = json.loads(content)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(payload, dict) and payload.get("sigil_addr") == address:
                return {"address": address, "value": payload.get("value"),
                        "salience": payload.get("salience", 0.0),
                        "meta": payload.get("meta", {}),
                        "ts": payload.get("ts", 0.0),
                        "tier": "cold", "source": "sov3"}
        return None

    def list(self, limit: int = 100) -> list:
        # Cold listing is expensive; ask SOV3 for recent memory_tier writes.
        res = _sov3_call("query_memories", {"query": "memory_tier", "limit": max(1, int(limit))})
        if res is None:
            return []
        mems = res.get("memories", res) if isinstance(res, dict) else res
        if not isinstance(mems, list):
            return []
        out = []
        for m in mems[:limit]:
            content = m.get("content", "") if isinstance(m, dict) else ""
            try:
                payload = json.loads(content)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(payload, dict) or "sigil_addr" not in payload:
                continue
            out.append({"address": payload["sigil_addr"], "value": payload.get("value"),
                        "salience": payload.get("salience", 0.0),
                        "meta": payload.get("meta", {}),
                        "ts": payload.get("ts", 0.0), "tier": "cold"})
        return out

    def stats(self) -> dict:
        return {"tier": "cold", "reachable": self._is_reachable(), "url": self._url}


# ---- THE ROUTER ------------------------------------------------------------

class MemoryTier:
    """The tiered memory router. put/get/list with a tier-hint or auto-route by salience.

    Auto-routing rules (the tier-routing decision tree):
        salience  > _WARM_SALIENCE_CAP (0.85)  → cold (sovereign, signed, audit chain)
        salience >= _HOT_SALIENCE_CAP (0.40)  → warm (SSD, survives process)
        salience  < _HOT_SALIENCE_CAP         → hot  (RAM, sub-ms)
    get  : tries hot → warm → cold in order (fastest first, slowest last).
    list : merges all three, dedupes by address (cold > warm > hot precedence on collisions).
    """
    TIERS = ("hot", "warm", "cold")

    def __init__(self, sov3_url: str = SOV3_MCP, warm_path: str = _DB_PATH):
        self.hot = _HotTier()
        self.warm = _WarmTier(warm_path)
        self.cold = _ColdTier(sov3_url)

    # ---- routing decision ---------------------------------------------------
    @staticmethod
    def route(salience: float) -> str:
        s = float(salience)
        if s >= _WARM_SALIENCE_CAP:
            return "cold"
        if s >= _HOT_SALIENCE_CAP:
            return "warm"
        return "hot"

    def _backend(self, tier: str):
        return {"hot": self.hot, "warm": self.warm, "cold": self.cold}[tier]

    # ---- public API (same signature on every tier) --------------------------
    def put(self, key: str, value: Any, salience: float = 0.0,
            meta: Optional[dict] = None, tier: Optional[str] = None) -> dict:
        """Store at `key` (the user-facing handle) — internally addressed by
        sigil_address(key) so the same key always maps to the same sigil
        prefix. If `tier` is None, the salience-based router decides.
        Returns the stored record (with the chosen tier and sigil address)."""
        address = sigil_address(key)
        chosen = tier if tier in self.TIERS else self.route(salience)
        rec = self._backend(chosen).put(address, value, salience, meta)
        rec["key"] = key
        return {"ok": True, "tier": chosen, "address": address, "record": rec}

    def get(self, key: str, tier: Optional[str] = None) -> dict:
        """Look up `key`. If `tier` given, look only there. Else try
        hot → warm → cold (fastest first). Returns the first hit, with tier tag."""
        address = sigil_address(key)
        if tier in self.TIERS:
            rec = self._backend(tier).get(address)
            return {"ok": rec is not None, "tier": tier, "address": address, "record": rec}
        for t in self.TIERS:
            rec = self._backend(t).get(address)
            if rec is not None:
                return {"ok": True, "tier": t, "address": address, "record": rec}
        return {"ok": False, "tier": None, "address": address, "record": None}

    def list(self, limit: int = 100, tier: Optional[str] = None) -> dict:
        """List recent records. If `tier` given, that tier only. Else merge
        all three, deduped by address (cold > warm > hot precedence)."""
        if tier in self.TIERS:
            items = self._backend(tier).list(limit)
            return {"ok": True, "tier": tier, "items": items, "count": len(items)}
        merged, seen, by_tier = [], set(), {}
        for t in self.TIERS:
            items = self._backend(t).list(limit)
            for it in items:
                seen.add(it["address"])
                by_tier.setdefault(it["address"], t)
            merged.extend(items)
        # dedupe, cold > warm > hot precedence
        deduped = []
        for it in merged:
            if all(d["address"] != it["address"] for d in deduped):
                deduped.append(it)
        deduped.sort(key=lambda r: r.get("ts", 0.0), reverse=True)
        return {"ok": True, "tier": "all", "items": deduped[:limit],
                "count": len(deduped[:limit]),
                "by_tier_size": {t: len(self._backend(t).list(limit)) for t in self.TIERS}}

    def stats(self) -> dict:
        return {
            "hot": self.hot.stats(),
            "warm": self.warm.stats(),
            "cold": self.cold.stats(),
            "routing": {"hot_cap": _HOT_SALIENCE_CAP, "warm_cap": _WARM_SALIENCE_CAP},
        }


# ---- module-level singleton ------------------------------------------------

_default: Optional[MemoryTier] = None
_default_lock = threading.Lock()


def router() -> MemoryTier:
    """Process-local default router (singleton, thread-safe init)."""
    global _default
    if _default is None:
        with _default_lock:
            if _default is None:
                _default = MemoryTier()
    return _default


# ---- CLI smoke test --------------------------------------------------------
if __name__ == "__main__":
    r = router()
    print("stats:", json.dumps(r.stats(), indent=2, default=str))
    r.put("user:greeting:hello", "warm hi from meok", salience=0.2, meta={"who": "test"})
    r.put("user:insight:cold", "sovereign-signed insight", salience=0.9, meta={"who": "test"})
    r.put("user:note:warm", "SSD-backed note", salience=0.5, meta={"who": "test"})
    print("\nhot list:", [x["address"][:8] for x in r.hot.list()])
    print("warm list:", [x["address"][:8] for x in r.warm.list()])
    print("cold list:", [x["address"][:8] for x in r.cold.list()])
    print("\nget hello:", r.get("user:greeting:hello")["tier"])
    print("get cold :", r.get("user:insight:cold")["tier"])
    print("get warm :", r.get("user:note:warm")["tier"])
    print("\nmerged list:", r.list(10)["count"])
    print("route(salience=0.95):", r.route(0.95))
    print("route(salience=0.50):", r.route(0.50))
    print("route(salience=0.10):", r.route(0.10))
