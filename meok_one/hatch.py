"""
MEOK ONE — Stage 3: the hatch flow.

The consumer onboarding. An egg 🥚 cracks into the consumer's personal care-director:

    1. Consumer is shown the 8 archetypes + 5 care-styles (the customisable options)
    2. They choose archetype + care-style + a name
    3. The egg hatches -> a matching character is selected + becomes their endpoint
    4. They talk to it (Stage 2 brain) — and as they engage, XP grows the character
       through the emergence stages: 🥚 egg -> 🐣 cracking -> ✨ hatching -> 🌱 growing
       -> 🌟 mature -> 👑 full sovereign

This module is headless (data + logic). A real UI (web/Amica 3D avatar/TUI) drives it.
hatch_session() runs the whole flow non-interactively for testing/demo.
"""

from .registry import Registry, default
from .brain import Character


class HatchSession:
    """One consumer's hatch + ongoing bond. XP accrues per interaction and
    advances the character through emergence stages."""

    def __init__(self, registry: Registry = None):
        self.reg = registry or default()
        self.xp = 0
        self.config = None       # the hatched character config
        self.character = None    # live Character (brain)

    # ---- the customisable options shown at onboarding ----
    def options(self) -> dict:
        return {
            "archetypes": [{"id": a["id"], "label": a["label"],
                            "description": a["description"], "emoji": a["emoji"],
                            "color": a["color"]} for a in self.reg.archetypes()],
            "care_styles": self.reg.care_styles(),
            "stages": self.reg.emergence_stages(),
        }

    # ---- the hatch event ----
    def hatch(self, archetype_id: str, care_style: str = None, name: str = None) -> dict:
        """Crack the egg. Returns the hatched care-director config + the reveal."""
        self.config = self.reg.hatch(archetype_id=archetype_id, care_style=care_style,
                                     name=name, xp=self.xp)
        self.character = Character(self.config["character_id"], registry=self.reg)
        # the character speaks its first words on hatching, in-character
        stage = self.reg.hatch_stage(self.xp)
        return {
            "hatched": True,
            "name": self.config["name"],
            "character_id": self.config["character_id"],
            "archetype": self.config["archetype"],
            "care_style": self.config["care_style"],
            "stage": stage["id"], "stage_emoji": stage["emoji"],
            "visual": self.config["visual"],
            "voice": self.config["voice"],
            "tagline": self.config["tagline"],
        }

    # ---- ongoing bond ----
    def talk(self, message: str, xp_gain: int = 5) -> dict:
        """Consumer talks to their care-director. Each exchange grows the bond (XP)
        and may advance the emergence stage."""
        if self.character is None:
            raise RuntimeError("hatch a character before talking to it")
        before = self.reg.hatch_stage(self.xp)["id"]
        out = self.character.say(message)
        self.xp += xp_gain
        after = self.reg.hatch_stage(self.xp)
        out["xp"] = self.xp
        out["stage"] = after["id"]
        out["stage_emoji"] = after["emoji"]
        out["leveled_up"] = (after["id"] != before)
        out["progress_to_next"] = after["progress_to_next"]
        return out


def hatch_session(archetype="nurturer", care_style="gentle", name="Bramble",
                  messages=None) -> dict:
    """Run a full hatch + conversation flow non-interactively. Returns a transcript."""
    s = HatchSession()
    reveal = s.hatch(archetype, care_style, name)
    transcript = {"reveal": reveal, "exchanges": []}
    for m in (messages or ["Hi, I just hatched you. Who are you?"]):
        transcript["exchanges"].append({"you": m, "reply": s.talk(m)})
    transcript["final_xp"] = s.xp
    transcript["final_stage"] = s.reg.hatch_stage(s.xp)["id"]
    return transcript


if __name__ == "__main__":
    import json
    print("=" * 64)
    print("MEOK ONE — HATCH FLOW DEMO")
    print("=" * 64)
    s = HatchSession()
    opts = s.options()
    print(f"\n🥚 Choose your care-director's nature ({len(opts['archetypes'])} archetypes):")
    for a in opts["archetypes"]:
        print(f"   {a['emoji']}  {a['label']:18} — {a['description'][:50]}")
    print(f"\n   ...and {len(opts['care_styles'])} care styles: {', '.join(opts['care_styles'])}")

    print("\n🐣 Consumer picks: archetype=nurturer, care_style=gentle, name='Bramble'")
    reveal = s.hatch("nurturer", "gentle", "Bramble")
    print(f"\n✨ HATCHED: {reveal['name']} {reveal['visual']['emoji']} "
          f"(based on {reveal['character_id']}, {reveal['archetype']}/{reveal['care_style']})")
    print(f"   stage: {reveal['stage_emoji']} {reveal['stage']}  ·  \"{reveal['tagline']}\"")

    print("\n💬 First conversation (each exchange grows the bond):")
    for msg in ["Hi Bramble. I just hatched you — I'm a bit nervous about all this.",
                "I want you to help me feel less overwhelmed day to day."]:
        out = s.talk(msg)
        lvl = "  ⬆️ LEVELED UP!" if out.get("leveled_up") else ""
        print(f"\n   YOU: {msg}")
        print(f"   {reveal['name'].upper()} {out['emoji']} [{out['source']}, xp={out['xp']} {out['stage_emoji']}{lvl}]:")
        print(f"   {out['reply']}")
