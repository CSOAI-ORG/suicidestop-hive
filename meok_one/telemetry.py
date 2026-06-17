"""
MEOK ONE — TELEMETRY: cross-hive, anonymised learning substrate.

Each hive queen publishes *aggregate, non-sensitive* metrics after an interaction:
safety outcome, latency bucket, domain, and a capability tag. Raw user Q/A is NEVER
written here. ASI-Evolve and other protocol hives consume this stream to learn across
the empire without violating hive boundaries.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import Counter
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

_TELEMETRY_LOG = os.environ.get(
    "MEOK_TELEMETRY_LOG",
    os.path.join(os.path.dirname(__file__), "data", "telemetry.jsonl"),
)
_TELEMETRY_LOCK = threading.RLock()


def _safe_json(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"), default=str)


def publish(hive: str, event_type: str, payload: dict[str, Any]) -> dict:
    """Append one anonymised telemetry event. Thread/process safe."""
    event = {
        "ts": time.time(),
        "hive": hive,
        "type": event_type,
        "payload": payload,
    }
    line = _safe_json(event)
    try:
        os.makedirs(os.path.dirname(_TELEMETRY_LOG), exist_ok=True)
        with open(_TELEMETRY_LOG, "a+") as f:
            if fcntl:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(line + "\n")
                f.flush()
            finally:
                if fcntl:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return {"ok": True, "event": event}
    except Exception as e:
        return {"ok": False, "error": type(e).__name__}


def recent(n: int = 100) -> list[dict[str, Any]]:
    """Return the last n telemetry events."""
    out: list[dict[str, Any]] = []
    try:
        with open(_TELEMETRY_LOG) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception:
        return out
    return out[-n:] if n < len(out) else out


def aggregate(window_seconds: float = 3600.0) -> dict[str, Any]:
    """Aggregate recent telemetry into per-hive metrics for ASI-Evolve."""
    cutoff = time.time() - window_seconds
    events = [e for e in recent(10000) if e.get("ts", 0) >= cutoff]

    by_hive: dict[str, dict[str, Any]] = {}
    for e in events:
        hive = e.get("hive", "unknown")
        payload = e.get("payload", {})
        if hive not in by_hive:
            by_hive[hive] = {"events": 0, "safe": 0, "unsafe": 0, "latencies": [], "tags": Counter()}
        bucket = by_hive[hive]
        bucket["events"] += 1
        bucket["safe"] += 1 if payload.get("safe") else 0
        bucket["unsafe"] += 0 if payload.get("safe") else 1
        if "latency_ms" in payload:
            bucket["latencies"].append(payload["latency_ms"])
        for tag in payload.get("tags", []):
            bucket["tags"][tag] += 1

    summary = {}
    for hive, bucket in by_hive.items():
        latencies = bucket.pop("latencies")
        summary[hive] = {
            **bucket,
            "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
            "tags": dict(bucket["tags"]),
        }

    return {
        "window_seconds": window_seconds,
        "total_events": len(events),
        "hives": summary,
    }
