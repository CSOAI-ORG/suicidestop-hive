"""
MEOK ONE — Canonical Character Registry.

THE single source of truth for MEOK's 27 characters, 8 archetypes, 5 care-styles,
and 6 hatch (emergence) stages. Every surface — SaaS, TUI, voice, inner-LLMs,
the Amica 3D avatar — reads from HERE, not from one of the (now-deprecated) 4
duplicate character_factory.py copies scattered across the tree.

Pure stdlib. Data lives in characters.json next to this module.

Public API:
    reg = Registry()
    reg.list_characters()              -> [ {id,name,tagline,archetype,care_style,tier,...} ]
    reg.get(char_id)                   -> full character dict
    reg.archetypes()                   -> the 8 archetypes (label, colour, emoji, members)
    reg.care_styles()                  -> the 5 care-style definitions
    reg.hatch_stage(xp)                -> which emergence stage an XP total is at
    reg.persona(char_id)               -> the LLM system prompt for that character
    reg.voice(char_id)                 -> TTS/voice params (ElevenLabs-ready)
    reg.visual(char_id)                -> colour/emoji/gradient for the UI
    reg.unlocked(char_id, xp)          -> is this character available at this XP yet?
    reg.available(xp, tier="free")     -> characters a consumer can hatch right now
"""

import json
import os

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "characters.json")

# Hatch stage order (matches characters.json emergence_stages)
_STAGE_ORDER = ["egg", "cracking", "hatching", "growing", "mature", "full"]


class Registry:
    def __init__(self, path: str = _DATA):
        with open(path, encoding="utf-8") as f:
            self._d = json.load(f)
        self._by_id = {c["id"]: c for c in self._d["characters"]}

    # ---- meta ----
    @property
    def version(self) -> str:
        return self._d.get("version", "?")

    @property
    def total(self) -> int:
        return len(self._d["characters"])

    def archetypes(self) -> list:
        """The 8 archetypes: id, label, description, colour, emoji, member character ids."""
        return self._d["archetypes"]

    def care_styles(self) -> dict:
        """The 5 care-style definitions (how the character cares)."""
        return self._d["care_styles"]

    def emergence_stages(self) -> dict:
        return self._d["emergence_stages"]

    # ---- characters ----
    def list_characters(self) -> list:
        """Lightweight listing for menus/cards."""
        return [{
            "id": c["id"], "name": c["name"], "tagline": c["tagline"],
            "archetype": c["archetype"], "care_style": c["care_style"],
            "tier": c.get("tier", "free"), "emoji": c["visual"]["emoji"],
            "unlock": c.get("emergence_stage_unlock", "egg"),
            "pack": c.get("pack"),   # e.g. "faith" → hidden from the default roster (opt-in)
        } for c in self._d["characters"]]

    def get(self, char_id: str) -> dict:
        c = self._by_id.get(char_id.lower())
        if c is None:
            raise KeyError(f"unknown character: {char_id!r} (have {len(self._by_id)})")
        return c

    def register(self, char: dict) -> str:
        """Add a character (e.g. factory-minted) so get()/brain/voice/act load it by id.
        Validates required fields so a broken character can't enter the runtime.
        In-memory only — the canonical JSON stays the 27 hand-crafted seeds."""
        required = {"id", "name", "archetype", "care_style", "system_prompt_prefix",
                    "voice", "visual", "tier"}
        missing = required - set(char)
        if missing:
            raise ValueError(f"cannot register character: missing fields {sorted(missing)}")
        self._by_id[char["id"].lower()] = char
        return char["id"]

    def register_many(self, chars: list) -> int:
        """Register a batch; returns how many were added."""
        for c in chars:
            self.register(c)
        return len(chars)

    def persona(self, char_id: str) -> str:
        """The system prompt prefix an LLM adopts to BE this character."""
        return self.get(char_id)["system_prompt_prefix"]

    def voice(self, char_id: str) -> dict:
        return self.get(char_id)["voice"]

    def visual(self, char_id: str) -> dict:
        return self.get(char_id)["visual"]

    # ---- hatch / emergence ----
    def hatch_stage(self, xp: int) -> dict:
        """Which emergence stage an XP total corresponds to. Returns the stage dict
        plus its id and progress toward the next stage."""
        stages = self._d["emergence_stages"]
        current = "egg"
        for sid in _STAGE_ORDER:
            if xp >= stages[sid]["threshold"]:
                current = sid
        idx = _STAGE_ORDER.index(current)
        nxt = _STAGE_ORDER[idx + 1] if idx + 1 < len(_STAGE_ORDER) else None
        out = dict(stages[current])
        out["id"] = current
        out["next"] = nxt
        if nxt:
            span = stages[nxt]["threshold"] - stages[current]["threshold"]
            done = xp - stages[current]["threshold"]
            out["progress_to_next"] = round(done / span, 3) if span else 1.0
            out["xp_to_next"] = stages[nxt]["threshold"] - xp
        else:
            out["progress_to_next"] = 1.0
            out["xp_to_next"] = 0
        return out

    def unlocked(self, char_id: str, xp: int) -> bool:
        """Is this character available to a consumer at this XP level yet?"""
        need = self.get(char_id).get("emergence_stage_unlock", "egg")
        return xp >= self._d["emergence_stages"][need]["threshold"]

    def available(self, xp: int = 0, tier: str = "free") -> list:
        """Characters a consumer can hatch right now, given XP + subscription tier."""
        tiers = {"free": {"free"}, "pro": {"free", "pro"},
                 "gaming": {"free", "pro", "gaming"}}.get(tier, {"free"})
        return [c["id"] for c in self._d["characters"]
                if c.get("tier", "free") in tiers and self.unlocked(c["id"], xp)]

    # ---- the hatch event ----
    def hatch(self, archetype_id: str = None, care_style: str = None,
              name: str = None, xp: int = 0) -> dict:
        """Hatch a consumer's care-director: pick the best-matching character for the
        chosen archetype + care_style (the customisable options), at the consumer's
        current hatch stage. Returns a ready-to-run character config.

        This is what the consumer onboarding calls when the egg cracks."""
        candidates = self._d["characters"]
        if archetype_id:
            candidates = [c for c in candidates
                          if archetype_id in (c.get("archetypes") or [c.get("archetype")])]
        if care_style:
            cs = [c for c in candidates if c.get("care_style") == care_style]
            candidates = cs or candidates
        # prefer an unlocked one at this xp
        unlocked = [c for c in candidates if self.unlocked(c["id"], xp)]
        chosen = (unlocked or candidates or self._d["characters"])[0]
        stage = self.hatch_stage(xp)
        return {
            "character_id": chosen["id"],
            "name": name or chosen["name"],
            "archetype": chosen["archetype"],
            "care_style": chosen["care_style"],
            "persona": chosen["system_prompt_prefix"],
            "voice": chosen["voice"],
            "visual": chosen["visual"],
            "hatch_stage": stage["id"],
            "stage_emoji": stage["emoji"],
            "tagline": chosen["tagline"],
        }


# module-level singleton for convenience
_default = None


def default() -> Registry:
    global _default
    if _default is None:
        _default = Registry()
    return _default
