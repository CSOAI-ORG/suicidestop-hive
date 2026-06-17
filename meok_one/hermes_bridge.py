"""
MEOK ONE — HERMES ↔ KING bridge.

Hermes (the comms/gateway layer — telegram/whatsapp, runs on the Mac) routes a user
message to the KING (king_ask → routed queen → SME answer) over HTTP. This is the link
that lets real users talk to the 29 hive queens.

The king binds to 127.0.0.1:8077 on the GCP VM, so Hermes reaches it via ONE of:
  - a token-gated tunnel  (KING_URL=https://king.meok.ai)   — set MEOK_KING_TOKEN
  - a relay/SSH-forward    (KING_URL=http://localhost:8077)  — when run on the VM
Until the king is exposed, this returns a clear "unreachable" envelope (never crashes
the gateway). The king enforces MEOK_KING_TOKEN when set, so exposure is safe.

Usage (from Hermes, or any gateway):
    from meok_one.hermes_bridge import ask_king
    out = ask_king("what licence for a grab lorry?")        # -> {"reply": ..., "routed_to": [...]}
CLI:
    python -m meok_one.hermes_bridge "koi pond ammonia is high"
"""
from __future__ import annotations

import json
import os
import urllib.request
import urllib.error

KING_URL = os.environ.get("KING_URL", "http://localhost:8077").rstrip("/")
KING_TOKEN = os.environ.get("MEOK_KING_TOKEN", "").strip()
DEFAULT_TIMEOUT = float(os.environ.get("KING_TIMEOUT", "120"))


def ask_king(message: str, *, fan_out: bool = False, k: int = 3,
             base_url: str | None = None, token: str | None = None,
             timeout: float | None = None) -> dict:
    """Route a user message through the king. Returns {reply, routed_to, mode, error?}.

    Best-effort: any transport/king error becomes {"error": ...} with a graceful reply,
    so a Hermes gateway never crashes on a king wobble."""
    base = (base_url or KING_URL).rstrip("/")
    tok = token if token is not None else KING_TOKEN
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "king_ask", "arguments": {"message": message, "fan_out": fan_out, "k": k}}}
    headers = {"Content-Type": "application/json"}
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(f"{base}/mcp", data=json.dumps(payload).encode(),
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout or DEFAULT_TIMEOUT) as r:
            env = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        code = e.code
        hint = " (set MEOK_KING_TOKEN to match the king)" if code == 403 else ""
        return {"error": f"king HTTP {code}{hint}", "reply":
                "[the hive is briefly unavailable — please try again]"}
    except Exception as e:  # noqa: BLE001 — gateway must never crash
        return {"error": f"{type(e).__name__}: king unreachable at {base}", "reply":
                "[the hive is briefly unavailable — please try again]"}
    content = (env.get("result", {}) or {}).get("content", [])
    if not content:
        return {"error": env.get("error", "empty king response"),
                "reply": "[the hive returned no answer — please try again]"}
    try:
        k_out = json.loads(content[0]["text"])
    except Exception:
        return {"reply": content[0].get("text", ""), "routed_to": []}
    return {"reply": k_out.get("reply", ""), "routed_to": k_out.get("routed_to", []),
            "mode": k_out.get("mode")}


if __name__ == "__main__":
    import sys
    msg = " ".join(sys.argv[1:]) or "what is MEOK?"
    res = ask_king(msg, fan_out=("--fan" in sys.argv))
    print(json.dumps(res, indent=2))
