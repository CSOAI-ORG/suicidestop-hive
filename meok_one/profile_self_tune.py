"""
PROFILE SELF-TUNE — read the latest quantum scores, compute the optimal
profile weights, write a sidecar /tmp/profile_weights.json that bridge.py
reads on every call, and announce the reweight to SOV3 via coord_submit_task.

How it works
============

1. Read /tmp/profile_quantum.json (produced by profile_quantum.py)
2. For each profile, take the normalised quantum weight
3. Convert the weights into per-(side, backend) model picks — i.e. for each
   profile P, the "winning" model for that profile's left/right is whatever
   side P had the highest care score on. We then also bias the sidecar so
   that the global "default" weights tilt toward the higher-scoring profiles.
4. Write /tmp/profile_weights.json (the sidecar) — bridge.py's
   _pick_with_weight() reads this on every call.
5. Submit a SOV3 task via coord_submit_task announcing the reweight (so the
   other queens see it in the coord dashboard).

The loop can run as a one-shot CLI or as a cron-friendly daemon.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Optional

from .profile_quantum import latest_quantum, _QUANTUM_OUT
from .bridge import _PROFILES, _PROFILE_WEIGHTS_PATH

# SOV3 coord MCP — same default the OLM tournament uses
_SOV3 = os.environ.get("SOV3_MCP", "http://localhost:3101/mcp")
_TIMEOUT = int(os.environ.get("MEOK_SELF_TUNE_TIMEOUT", "8"))
_SELF_TUNE_LOG = "/tmp/profile_self_tune.json"


# ---- the weighting algorithm -----------------------------------------------

def compute_optimal_weights(quantum: dict) -> dict:
    """From the latest quantum scores, compute the optimal profile weights.

    Output shape:
        {
          "<profile>": {
            "left:local":  "<model>",
            "right:cloud": "<model>",
            ...
            "weight":     0.0..1.0,
            "win_rate":   0.0..1.0,
            "avg_care":   0.0..10.0,
            "gate":       "PASS"|"FAIL",
          }
        }
    """
    norm = quantum.get("norm_weights") or {}
    wins = quantum.get("win_rates") or {}
    per = quantum.get("per_profile") or {}

    out: dict = {}
    for prof in _PROFILES.keys():
        s = per.get(prof, {}) or {}
        weight = float(norm.get(prof, 0.0))
        win_rate = float(wins.get(prof, 0.0))
        avg_care = s.get("avg_care_score")
        gate = s.get("gate", "FAIL")
        # For each (side, backend) the profile declares, decide the model.
        # We start from bridge._PICK and then let the per-profile overrides
        # (e.g. health → medllama2 / compliance-llm) win.
        from . import bridge as _bridge
        _profiles = _bridge._PROFILES  # type: ignore[attr-defined]
        _pick = _bridge._PICK          # type: ignore[attr-defined]
        sides = _profiles[prof]
        picks: dict = {}
        for side, backends in (("left", sides.get("left") or []),
                               ("right", sides.get("right") or [])):
            for backend in backends:
                # 3-tuple wins for health, 2-tuple wins for the others
                m = (_pick.get((prof, side, backend))
                     or _pick.get((side, backend))
                     or "auto")
                picks[f"{side}:{backend}"] = m
        out[prof] = {
            **picks,
            "weight": round(weight, 4),
            "win_rate": round(win_rate, 4),
            "avg_care": avg_care,
            "gate": gate,
        }
    return out


def write_sidecar(weights: dict, path: str = _PROFILE_WEIGHTS_PATH) -> str:
    """Atomically write the sidecar so bridge._pick_with_weight picks it up
    on the very next call. Returns the path written."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(weights, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


# ---- SOV3 announcement -----------------------------------------------------

def _sov3_call(tool: str, arguments: dict, timeout: int = _TIMEOUT) -> Optional[dict]:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": tool, "arguments": arguments}}
    req = urllib.request.Request(_SOV3, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Accept": "application/json, text/event-stream"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode()
        if "data:" in body:
            body = [l[5:].strip() for l in body.splitlines() if l.startswith("data:")][-1]
        env = json.loads(body)
        if "error" in env:
            return None
        return env.get("result")
    except Exception:
        return None


def announce_to_sov3(weights: dict, quantum: dict) -> Optional[dict]:
    """Submit a SOV3 coord task announcing the reweight so other queens see it
    in the coordination dashboard. Best-effort — never raises."""
    ts = int(time.time())
    # human-readable title for the dashboard
    ranking = sorted(((p, w["weight"]) for p, w in weights.items()),
                     key=lambda kv: -kv[1])
    title = f"profile_self_tune @ {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(ts))} UTC"
    description_lines = [
        f"OLM quantum ran over all 5 bridge profiles "
        f"(baseline_care={quantum.get('baseline_care')}).",
        "",
        "New weights (normalised quantum score):",
    ]
    for prof, w in ranking:
        marker = "✓" if weights[prof]["gate"] == "PASS" else "✗"
        description_lines.append(
            f"  {marker} {prof:<11} weight={w:.3f}  "
            f"win_rate={weights[prof]['win_rate']:.3f}  "
            f"care={weights[prof]['avg_care']}  "
            f"gate={weights[prof]['gate']}"
        )
    description_lines += [
        "",
        f"Sidecar written → {_PROFILE_WEIGHTS_PATH}",
        "bridge._pick_with_weight() will pick this up on the next call.",
    ]
    description = "\n".join(description_lines)
    files = [
        _PROFILE_WEIGHTS_PATH,
        _QUANTUM_OUT,
        _SELF_TUNE_LOG,
    ]
    res = _sov3_call("coord_submit_task", {
        "title": title,
        "description": description,
        "files": [f for f in files if os.path.exists(f)],
        # care_score: pass the best (highest weighted) profile's avg_care
        "care_score": max((w.get("avg_care") or 0.0) for w in weights.values()),
    })
    # also push a memory line so the hive sees it
    try:
        _sov3_call("record_memory", {
            "content": title + " | " + " | ".join(
                f"{p}={w['weight']:.2f}" for p, w in ranking
            ),
            "source_agent": "profile-self-tune",
            "memory_type": "hive_honey",
            "importance": 0.75,
            "tags": ["profile_self_tune", "olm_quantum", "reweight"],
        })
    except Exception:
        pass
    return res


# ---- the public entry point -------------------------------------------------

def self_tune(quantum_path: str = _QUANTUM_OUT,
              sidecar_path: str = _PROFILE_WEIGHTS_PATH,
              announce: bool = True) -> dict:
    """Read the latest quantum, compute weights, write the sidecar, announce.

    Returns the summary dict (also written to /tmp/profile_self_tune.json).
    """
    quantum = latest_quantum(quantum_path)
    if quantum.get("status") != "ok":
        return {
            "status": "skipped",
            "reason": quantum.get("message", "no quantum on disk"),
            "ts": int(time.time()),
        }
    weights = compute_optimal_weights(quantum)
    path = write_sidecar(weights, sidecar_path)

    sov3 = None
    if announce:
        sov3 = announce_to_sov3(weights, quantum)

    summary = {
        "status": "ok",
        "ts": int(time.time()),
        "quantum_ts": quantum.get("ts"),
        "character": quantum.get("character"),
        "weights": weights,
        "sidecar_path": path,
        "sov3_task": (sov3 or {}).get("content") if sov3 else None,
        "sov3_announced": bool(sov3),
    }
    try:
        with open(_SELF_TUNE_LOG, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return summary


def latest_self_tune(path: str = _SELF_TUNE_LOG) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        d.setdefault("status", "ok")
        d["path"] = path
        return d
    except FileNotFoundError:
        return {"status": "empty", "message": "no self_tune on disk yet", "path": path}
    except Exception as e:
        return {"status": "error", "message": f"failed to read self_tune: {e}",
                "path": path}


# ---- the daemon loop --------------------------------------------------------

def run_loop(every_s: int = 600, max_runs: Optional[int] = None) -> None:
    """Cron-friendly loop. every_s = seconds between self-tunes. max_runs is
    None for infinite (use for a foreground daemon)."""
    runs = 0
    print(f"[profile_self_tune] loop start · every {every_s}s · max {max_runs}")
    while True:
        s = self_tune()
        print(f"  · run {runs + 1}: {s.get('status')}",
              f"weights={list((s.get('weights') or {}).keys())[:3]}...")
        runs += 1
        if max_runs is not None and runs >= max_runs:
            print("[profile_self_tune] loop done")
            return
        time.sleep(every_s)


# ---- CLI --------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "loop":
        every = int(sys.argv[2]) if len(sys.argv) > 2 else 600
        max_r = int(sys.argv[3]) if len(sys.argv) > 3 else None
        run_loop(every_s=every, max_runs=max_r)
    else:
        s = self_tune()
        print(json.dumps({
            "status": s.get("status"),
            "ts": s.get("ts"),
            "sidecar": s.get("sidecar_path"),
            "weights": s.get("weights"),
            "sov3_announced": s.get("sov3_announced"),
        }, indent=2, default=str))
