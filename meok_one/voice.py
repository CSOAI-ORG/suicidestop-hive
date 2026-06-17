"""
MEOK ONE — Voice layer (voice-first sovereign).

Nick's ask: "make it mainly speech." A character should LISTEN and SPEAK, not just
type. This module turns a text reply into a fully-specified voice utterance using the
character's own voice params (already in the registry: ElevenLabs stability/similarity/
style/voice_id + pitch/rate + a recommended voice).

Honest scope: this assembles the VOICE SPEC — everything a TTS backend or frontend
needs to actually make sound. It does NOT fake audio it can't produce (no ElevenLabs
key here, no mic/speakers in a headless context). The audio I/O is the frontend's job
(browser Web Speech API for STT; ElevenLabs or browser SpeechSynthesis for TTS). What
this gives you is the contract every surface (web, TUI, Amica 3D avatar) renders.

    tts_spec(character, text)        -> the synthesis request (params + text)
    voice_reply(character, message)  -> brain reply + tts_spec, in one call (the loop)
    pipeline_status()                -> is SOV3's live voice pipeline up?
    stt_hint()                       -> how the frontend should capture speech
"""

import json
import urllib.request
import urllib.error

from .registry import default
from .brain import Character

SOV3_MCP = "http://localhost:3101/mcp"


def tts_spec(character_id: str, text: str) -> dict:
    """Everything a TTS backend needs to speak `text` AS this character.
    Maps the registry's voice params to an ElevenLabs-shaped request + a
    browser-SpeechSynthesis fallback (pitch/rate) so any surface can render it."""
    c = default().get(character_id)
    v = c["voice"]
    return {
        "character": c["name"],
        "text": text,
        "engine_preference": ["elevenlabs", "browser_speech_synthesis"],
        "elevenlabs": {
            "voice_id": v.get("elevenlabs_voice_id"),     # None -> use recommended_voice by name
            "recommended_voice": v.get("recommended_voice"),
            "stability": v.get("elevenlabs_stability"),
            "similarity_boost": v.get("elevenlabs_similarity"),
            "style": v.get("elevenlabs_style"),
            "model_id": "eleven_turbo_v2_5",
        },
        "browser_fallback": {                              # Web SpeechSynthesis params
            "pitch": v.get("pitch", 1.0),
            "rate": v.get("rate", 1.0),
            "voice_style_hint": v.get("style", ""),
        },
        "note": "Render with ElevenLabs if a key is configured; else the browser fallback "
                "(pitch/rate) keeps it voice-first with zero cost. Audio I/O is the surface's job.",
    }


def voice_reply(character_id: str, message: str, max_sentences: int = 3) -> dict:
    """The voice loop: a spoken-length reply from the character + the TTS spec to
    speak it. Keeps replies short (voice should be conversational, not an essay)."""
    ch = Character(character_id, max_sentences=max_sentences)
    out = ch.say(message)
    spec = tts_spec(character_id, out["reply"])
    return {
        "character": out["character"],
        "id": out["id"],
        "emoji": out["emoji"],
        "reply_text": out["reply"],
        "reply_source": out["source"],      # sov3:hermes / offline-stub etc — honest
        "tts": spec,
    }


def stt_hint() -> dict:
    """How a frontend should capture the user's speech. We don't run a mic here, so
    we specify the contract rather than pretend to transcribe."""
    return {
        "preferred": "browser_web_speech_api",   # SpeechRecognition — free, on-device
        "fallback": "whisper (local or API) for higher accuracy / non-Chrome",
        "flow": "capture speech -> text -> voice_reply(character, text) -> play tts",
        "note": "Voice-first: the user speaks, the character speaks back. STT is the "
                "frontend's capture step; this module handles character + voice spec.",
    }


def pipeline_status() -> dict:
    """Is SOV3's live voice pipeline up? Calls get_voice_pipeline_status; honest if down."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "get_voice_pipeline_status", "arguments": {}}}
    req = urllib.request.Request(SOV3_MCP, method="POST", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Accept": "application/json, text/event-stream"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            body = r.read().decode()
    except (urllib.error.URLError, TimeoutError, OSError):
        return {"sov3_voice": "unreachable", "note": "SOV3 offline; use browser TTS/STT"}
    if "data:" in body:
        lines = [l[5:].strip() for l in body.splitlines() if l.startswith("data:")]
        body = lines[-1] if lines else body
    try:
        env = json.loads(body)
        content = env.get("result", {}).get("content", [])
        if content and content[0].get("type") == "text":
            return {"sov3_voice": "online", "detail": json.loads(content[0]["text"])}
    except (json.JSONDecodeError, KeyError, IndexError):
        pass
    return {"sov3_voice": "unknown", "note": "pipeline status unparseable; browser TTS still works"}


if __name__ == "__main__":
    import sys
    cid = sys.argv[1] if len(sys.argv) > 1 else "aria"
    msg = sys.argv[2] if len(sys.argv) > 2 else "I'm feeling a bit overwhelmed today."
    out = voice_reply(cid, msg)
    print(f"=== voice_reply: {out['character']} {out['emoji']} ===")
    print(f"  [{out['reply_source']}] {out['reply_text']}")
    print(f"  voice: {out['tts']['elevenlabs']['recommended_voice']} "
          f"(stability {out['tts']['elevenlabs']['stability']}, "
          f"rate {out['tts']['browser_fallback']['rate']})")
