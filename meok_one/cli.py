#!/usr/bin/env python3
"""
meok-one — the unified CLI for the MEOK ONE OS.

One entry point over the whole package: hatch a character, talk to it, switch
models, see the pricing ladder, inspect live capabilities.

    meok-one hatch <archetype> <care_style> [name]   — hatch a care-director
    meok-one talk <character> "<message>"            — talk to a character (live)
    meok-one ask "<prompt>" [--model M] [--tier T]   — route a prompt to any model
    meok-one models [--tier T]                       — list switchable models
    meok-one tiers                                    — the pricing ladder
    meok-one capabilities [--tier T]                 — what a sovereign can do (live)
    meok-one characters                              — list the 27 characters
    meok-one version
"""
import argparse
import json
import sys

from . import (default, talk, HatchSession, ask, list_models, ladder,
               awareness_brief, voice_reply, __version__)


def _p(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False) if not isinstance(obj, str) else obj)


def cmd_characters(a):
    for c in default().list_characters():
        print(f"  {c['emoji']}  {c['id']:10} {c['name']:10} {c['archetype']:11} "
              f"{c['care_style']:10} [{c['tier']}]")


def cmd_hatch(a):
    s = HatchSession()
    r = s.hatch(a.archetype, a.care_style, a.name or None)
    print(f"{r['stage_emoji']} HATCHED: {r['name']} {r['visual']['emoji']} "
          f"(from {r['character_id']}, {r['archetype']}/{r['care_style']})")
    print(f'   "{r["tagline"]}"  ·  stage: {r["stage"]}')


def cmd_talk(a):
    out = talk(a.character, a.message)
    print(f"{out['character']} {out['emoji']} [{out['source']}]:")
    print(f"  {out['reply']}")


def cmd_ask(a):
    out = ask(a.prompt, model=a.model, tier=a.tier)
    print(f"[{out['backend']}/{out['source']}] {out.get('reply') or out.get('note')}")


def cmd_models(a):
    for m in list_models(a.tier):
        print(f"  {m['id']:16} {m['backend']:7} {m['concrete']}")


def cmd_tiers(a):
    for r in ladder():
        print(f"  {r['label']:24} {r['price']:22} {r['who']}")


def cmd_capabilities(a):
    print(awareness_brief(a.tier))


def cmd_say(a):
    out = voice_reply(a.character, a.message)
    tts = out["tts"]
    print(f"{out['character']} {out['emoji']} [{out['reply_source']}] (voice: "
          f"{tts['elevenlabs']['recommended_voice']}, rate {tts['browser_fallback']['rate']}):")
    print(f"  🔊 {out['reply_text']}")


def cmd_serve(a):
    from .server import main as serve_main
    serve_main(a.port)


def cmd_version(a):
    print(f"meok-one {__version__} — CSOAI LTD (trading as MEOK AI Labs)")


def build_parser():
    p = argparse.ArgumentParser(prog="meok-one", description="MEOK ONE — the unified character OS")
    sub = p.add_subparsers(dest="cmd")

    sv = sub.add_parser("serve", help="launch the web UX (hatch + talk in a browser)")
    sv.add_argument("--port", type=int, default=4173); sv.set_defaults(func=cmd_serve)

    sub.add_parser("characters", help="list the 27 characters").set_defaults(func=cmd_characters)

    h = sub.add_parser("hatch", help="hatch a care-director")
    h.add_argument("archetype"); h.add_argument("care_style"); h.add_argument("name", nargs="?")
    h.set_defaults(func=cmd_hatch)

    t = sub.add_parser("talk", help="talk to a character (live)")
    t.add_argument("character"); t.add_argument("message"); t.set_defaults(func=cmd_talk)

    sy = sub.add_parser("say", help="voice reply (text + TTS voice spec)")
    sy.add_argument("character"); sy.add_argument("message"); sy.set_defaults(func=cmd_say)

    k = sub.add_parser("ask", help="route a prompt to any model")
    k.add_argument("prompt"); k.add_argument("--model", default="auto"); k.add_argument("--tier", default="pro")
    k.set_defaults(func=cmd_ask)

    m = sub.add_parser("models", help="list switchable models")
    m.add_argument("--tier", default="pro"); m.set_defaults(func=cmd_models)

    sub.add_parser("tiers", help="pricing ladder").set_defaults(func=cmd_tiers)

    c = sub.add_parser("capabilities", help="what a sovereign can do (live)")
    c.add_argument("--tier", default="pro"); c.set_defaults(func=cmd_capabilities)

    sub.add_parser("version", help="version").set_defaults(func=cmd_version)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    if not getattr(args, "func", None):
        build_parser().print_help(); return 0
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
