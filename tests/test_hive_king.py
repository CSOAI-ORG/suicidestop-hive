"""Tests for the MEOK ONE hive KING — routing resilience + fan-out fault tolerance.
Pure/offline-safe: monkeypatches the classifier (`ask`), the hive catalog (`hives`)
and the `queen` so logic is deterministic without the VM/LLM.
Run: python3 tests/test_hive_king.py  (or pytest)"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import meok_one.hive_king as K  # noqa: E402


_CATALOG = [
    {"slug": "koikeeper", "scope": "koi pond water chemistry care", "tools": []},
    {"slug": "grabhire", "scope": "grab lorry hire haulage hgv", "tools": []},
    {"slug": "muckaway", "scope": "soil muck away tipping construction permits", "tools": []},
    {"slug": "commercialvehicle", "scope": "commercial vehicle fleet compliance", "tools": []},
]


def _patch(monkeypatch, reply):
    monkeypatch.setattr(K, "hives", lambda: _CATALOG)
    monkeypatch.setattr(K, "ask", lambda *a, **k: {"reply": reply})


def test_route_exact_slug(monkeypatch):
    _patch(monkeypatch, "grabhire")
    assert K.route("need a grab lorry") == ["grabhire"]


def test_route_near_miss_maps_to_valid_slug(monkeypatch):
    # classifier returns a close variant — should map to the one valid slug, not fall to keyword
    _patch(monkeypatch, "koikeeper-hive")
    assert K.route("koi ammonia spike") == ["koikeeper"]


def test_route_keyword_fallback_weights_scope(monkeypatch):
    # classifier down (empty reply) -> keyword fallback. The soil/tipping/construction
    # message must land on muckaway (the memory'd misroute was commercialvehicle).
    _patch(monkeypatch, "")
    assert K.route("I need to tip soil at a construction site, what permits?") == ["muckaway"]


def test_route_never_hard_fails(monkeypatch):
    # gibberish + dead classifier still returns a hive (thin+resilient contract)
    _patch(monkeypatch, "")
    got = K.route("zzzz qqqq")
    assert len(got) == 1 and got[0] in {h["slug"] for h in _CATALOG}


def test_king_survives_one_failing_queen(monkeypatch):
    monkeypatch.setattr(K, "route", lambda *a, **k: ["koikeeper", "grabhire", "muckaway"])
    monkeypatch.setattr(K, "ask", lambda *a, **k: {"reply": "sovereign synthesis"})

    def fake_queen(slug, message, **kw):
        if slug == "grabhire":
            raise RuntimeError("VM wobble")
        return {"reply": f"{slug} answer", "engine": "council", "safe": True, "governance": {}}

    monkeypatch.setattr(K, "queen", fake_queen)
    res = K.king("x", fan_out=True, k=3)
    # all 3 recorded, the failing one flagged, king did not crash
    assert len(res["queens"]) == 3
    errored = [q for q in res["queens"] if q.get("error")]
    assert len(errored) == 1 and errored[0]["hive"] == "grabhire"
    assert res["reply"] == "sovereign synthesis"


def test_king_deadline_abandons_hung_queen(monkeypatch):
    import time as _t
    monkeypatch.setattr(K, "route", lambda *a, **k: ["koikeeper", "grabhire"])
    monkeypatch.setattr(K, "ask", lambda *a, **k: {"reply": "synthesis"})

    def slow_queen(slug, message, **kw):
        if slug == "grabhire":
            _t.sleep(10)  # hang well past the deadline
        return {"reply": f"{slug} answer", "engine": "council", "safe": True, "governance": {}}

    monkeypatch.setattr(K, "queen", slow_queen)
    t0 = _t.monotonic()
    res = K.king("x", fan_out=True, k=2, deadline=0.5)
    elapsed = _t.monotonic() - t0
    assert elapsed < 5, f"king blocked on hung queen ({elapsed:.1f}s)"
    timed_out = [q for q in res["queens"] if q.get("error") == "timeout"]
    assert len(timed_out) == 1 and timed_out[0]["hive"] == "grabhire"
    # the fast queen still contributed
    assert any(q.get("reply") == "koikeeper answer" for q in res["queens"])


def test_king_all_queens_down_is_honest(monkeypatch):
    monkeypatch.setattr(K, "route", lambda *a, **k: ["koikeeper", "grabhire"])

    def dead_queen(slug, message, **kw):
        raise RuntimeError("down")

    monkeypatch.setattr(K, "queen", dead_queen)
    res = K.king("x", fan_out=True, k=2)
    assert "unavailable" in res["reply"]


if __name__ == "__main__":
    # minimal monkeypatch shim so it runs without pytest too
    class _MP:
        def __init__(self): self._undo = []
        def setattr(self, obj, name, val):
            old = getattr(obj, name); self._undo.append((obj, name, old)); setattr(obj, name, val)
        def undo(self):
            for obj, name, old in reversed(self._undo): setattr(obj, name, old)
            self._undo = []
    passed = 0
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        mp = _MP()
        try:
            fn(mp); print(f"  ✅ {fn.__name__}"); passed += 1
        except AssertionError as e:
            print(f"  ❌ {fn.__name__}: {e}")
        finally:
            mp.undo()
    print(f"\n{passed} passed")
