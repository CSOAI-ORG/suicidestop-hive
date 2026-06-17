"""
MEOK ONE — Stage 2: the live brain bridge.

Turns a character (from the canonical Registry) into a real talking endpoint:

    consumer message
        -> character.persona becomes the system_prompt
        -> SOV3's care-LLM (nemotron_chat) generates the reply IN CHARACTER
        -> reply comes back wearing the character's voice

This is the proof that "a character fronts the whole MEOK/SOV3 OS." The character
is the FACE + personality; SOV3 is the MIND. This module is the wire between them.

Verified live 2026-05-30: Aria's persona produced a genuinely in-character care
response from SOV3 (care_mode:true, ended with her 🌸).

Degrades honestly: if SOV3 is unreachable, returns a clearly-marked offline stub —
never fabricates a model response.
"""

import json
import re
import urllib.request
import urllib.error

from .registry import Registry, default

SOV3_MCP = "http://localhost:3101/mcp"


def _strip_thinking(text: str) -> str:
    """Remove <think>...</think> reasoning blocks that qwen3-class models emit
    before their answer, so the consumer sees only the reply. Falls back to the
    raw (stripped) text if that would leave nothing."""
    if not text:
        return text
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    if "<think>" in cleaned:  # unclosed/truncated think block
        cleaned = (cleaned.split("</think>")[-1] if "</think>" in cleaned
                   else cleaned.split("<think>")[-1])
    return cleaned.strip() or text.strip()


def _call_sov3(tool: str, args: dict, timeout: int = 30):
    """Call a SOV3 MCP tool. Returns parsed result dict, or None if unreachable."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": tool, "arguments": args}}
    req = urllib.request.Request(
        SOV3_MCP, method="POST", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode()
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    # MCP may SSE-frame the JSON
    if "data:" in body:
        lines = [l[5:].strip() for l in body.splitlines() if l.startswith("data:")]
        body = lines[-1] if lines else body
    try:
        env = json.loads(body)
        content = env.get("result", {}).get("content", [])
        if content and content[0].get("type") == "text":
            return json.loads(content[0]["text"])
        return env.get("result")
    except (json.JSONDecodeError, KeyError, IndexError):
        return None


class Character:
    """A live, talking character: registry config + SOV3 brain."""

    def __init__(self, char_id: str, registry: Registry = None, max_sentences: int = 4):
        self.reg = registry or default()
        self.c = self.reg.get(char_id)
        self.id = self.c["id"]
        self.name = self.c["name"]
        self.max_sentences = max_sentences

    def system_prompt(self) -> str:
        """The persona, plus a length nudge so consumer replies stay conversational."""
        return (f"{self.c['system_prompt_prefix']} "
                f"Keep replies to {self.max_sentences} sentences unless asked for more. "
                f"Stay fully in character as {self.name}.")

    def say(self, message: str, temperature: float = 0.7) -> dict:
        """Consumer says `message` -> character replies via SOV3. Returns
        {character, reply, source}. Honest offline fallback if SOV3 is down.

        Tries SOV3 LLM tools in order of what actually works:
          1. hermes_ask     — live + reliable (local Ollama qwen3 behind it)
          2. nemotron_chat  — has a system_prompt slot but upstream NVIDIA 404s often
        hermes_ask's only param is `prompt`, so the persona + message are framed into
        one prompt. Verified in-character live: Aria replied warmly + supportively."""
        # 1) hermes_ask — verified working. Its ONLY param is `prompt` (NOT question/
        # context) — passing the wrong name made it return a canned greeting. Persona +
        # message both go into prompt, framed so the model answers in character.
        personaed = f"{self.system_prompt()}\n\nUser: {message}\n\n{self.name}:"
        result = _call_sov3("hermes_ask", {"prompt": personaed})
        if result and result.get("response"):
            return {"character": self.name, "id": self.id,
                    "reply": _strip_thinking(result["response"]), "source": "sov3:hermes",
                    "emoji": self.c["visual"]["emoji"]}
        # 2) nemotron_chat — has a real system_prompt slot; use if hermes is down
        result = _call_sov3("nemotron_chat", {
            "message": message,
            "system_prompt": self.system_prompt(),
            "temperature": temperature,
            "max_tokens": 400,
        })
        if result and result.get("response"):
            return {"character": self.name, "id": self.id,
                    "reply": result["response"], "source": "sov3:nemotron",
                    "emoji": self.c["visual"]["emoji"]}
        # honest fallback — SOV3 unreachable
        return {"character": self.name, "id": self.id,
                "reply": f"[{self.name} is offline — SOV3 brain unreachable at "
                         f"{SOV3_MCP}. Persona is loaded; reconnect SOV3 to talk.]",
                "source": "offline-stub", "emoji": self.c["visual"]["emoji"]}


def talk(char_id: str, message: str, **kw) -> dict:
    """One-shot convenience: talk('aria', 'hi') -> reply dict."""
    return Character(char_id).say(message, **kw)


if __name__ == "__main__":
    import sys
    cid = sys.argv[1] if len(sys.argv) > 1 else "aria"
    msg = sys.argv[2] if len(sys.argv) > 2 else "I've had a long week. Just checking in."
    print(f"=== MEOK ONE brain: talking to {cid} ===")
    out = talk(cid, msg)
    print(f"\n  YOU: {msg}")
    print(f"  {out['character'].upper()} {out['emoji']} [{out['source']}]:")
    print(f"  {out['reply']}")
