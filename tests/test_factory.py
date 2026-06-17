"""Tests for the MEOK ONE character factory — 1000s of working characters.
Run: python3 tests/test_factory.py"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from meok_one.factory import mint, generate, space_size, _ARCHETYPES, _CARE  # noqa: E402
from meok_one.registry import Registry  # noqa: E402

_REQUIRED = {"id", "name", "tagline", "archetype", "archetypes", "care_style",
             "personality_traits", "voice", "visual", "domain", "backstory",
             "system_prompt_prefix", "proactivity", "best_for",
             "emergence_stage_unlock", "tier", "tags"}


def test_space_is_thousands():
    assert space_size() >= 4000   # 129 names x 8 archetypes x 5 care-styles


def test_mint_has_full_schema():
    c = mint("nurturer", "gentle", "Bramble")
    assert _REQUIRED <= set(c), f"missing {_REQUIRED - set(c)}"


def test_mint_is_deterministic():
    a = mint("challenger", "challenger", "Forge")
    b = mint("challenger", "challenger", "Forge")
    assert a["id"] == b["id"] and a["system_prompt_prefix"] == b["system_prompt_prefix"]


def test_mint_persona_coherent():
    c = mint("sage", "gentle", "Quill")
    p = c["system_prompt_prefix"]
    assert "Quill" in p and "wise" in p.lower() or "perspective" in p.lower()


def test_unknown_archetype_or_style_fails_loud():
    for bad in [("nope", "gentle", "X"), ("sage", "nope", "X")]:
        try:
            mint(*bad); assert False
        except KeyError:
            pass


def test_generate_distinct():
    batch = generate(1000)
    assert len(batch) == 1000
    assert len({c["id"] for c in batch}) == 1000   # all unique


def test_generate_rejects_over_capacity():
    try:
        generate(space_size() + 1); assert False
    except ValueError:
        pass


def test_minted_chars_are_dropin_registerable():
    reg = Registry()
    batch = generate(500)
    added = reg.register_many(batch)
    assert added == 500 and len(reg._by_id) == 527  # 27 seeds + 500
    # a registered minted char loads + has its persona
    c = reg.get(batch[250]["id"])
    assert c["name"] == batch[250]["name"]


def test_register_rejects_broken_character():
    reg = Registry()
    try:
        reg.register({"id": "x", "name": "Broken"})  # missing required fields
        assert False
    except ValueError:
        pass


def test_every_archetype_and_style_mints():
    for a in _ARCHETYPES:
        for s in _CARE:
            c = mint(a, s, f"T-{a}-{s}")
            assert c["archetype"] == a and c["care_style"] == s
            assert c["voice"]["recommended_voice"]  # non-empty voice


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn(); print(f"  PASS  {fn.__name__}"); passed += 1
        except Exception as e:
            print(f"  FAIL  {fn.__name__}: {e}")
    # bonus scale demo
    big = generate(2000)
    print(f"\n  [scale] generated {len(big):,} distinct working characters "
          f"(space: {space_size():,})")
    print(f"{passed}/{len(fns)} tests passed")
    return passed == len(fns)


if __name__ == "__main__":
    raise SystemExit(0 if _run() else 1)
