"""
MEOK ONE — VERIFIER: external, unfakeable gates + verifier-gated best-of-N.

The Level-0 keystone (2026-06-16). The deep-research verdict was blunt: a
self-improvement loop only measurably improves when scored by an EXTERNAL,
ground-truth signal the model cannot fake. "RLF till 100/100" graded by a
self-judge optimises the judge, not the goal. Compliance is one of the few
domains where free, unfakeable verifiers exist:

    json_valid        — does the output parse as JSON?
    schema_keys       — does it contain the required keys?
    citations_wellformed — are regulation article refs well-shaped + non-empty?
    attestation_verifies — does a referenced MEOK cert actually verify (live)?
    no_refusal        — did the SME actually answer (not deflect)?

A verifier returns a SCORE in [0,1] + a reason. `make_verifier` composes checks
(weighted mean). `best_of_n` generates N candidates and keeps the verifier-best
— the test-time half of self-improvement, and the one that provably helps when
the verifier is stronger than the generator (it is, when it's a real check).

`prove_improvement` runs best-of-1 vs best-of-N on a HELD-OUT suite and reports
the delta — the honest "did we get better" measurement (not a self-assigned 100).
"""
from __future__ import annotations

import json
import re
import statistics
import urllib.request
from typing import Callable

# A verifier: (candidate_text, task) -> (score in [0,1], reason)
Verifier = Callable[[str, dict], "tuple[float, str]"]


# ── individual external checks ──────────────────────────────────────────────
def _extract_json(text: str):
    """Pull the first JSON object/array out of a reply (models wrap it in prose)."""
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    start = next((i for i, c in enumerate(text) if c in "{["), -1)
    if start < 0:
        return None
    depth, instr, esc = 0, False, False
    for i in range(start, len(text)):
        c = text[i]
        if esc:
            esc = False; continue
        if c == "\\":
            esc = True; continue
        if c == '"':
            instr = not instr
        elif not instr:
            if c in "{[":
                depth += 1
            elif c in "}]":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        return None
    return None


def json_valid(text: str, task: dict) -> "tuple[float, str]":
    obj = _extract_json(text)
    return (1.0, "valid JSON") if obj is not None else (0.0, "no parseable JSON")


def schema_keys(text: str, task: dict) -> "tuple[float, str]":
    """Fraction of required keys present (in the object, or in each row of a list)."""
    req = task.get("required_keys") or []
    if not req:
        return (1.0, "no schema required")
    obj = _extract_json(text)
    if obj is None:
        return (0.0, "no JSON to check schema")
    rows = obj if isinstance(obj, list) else [obj]
    if not rows:
        return (0.0, "empty result")
    scores = []
    for row in rows:
        if not isinstance(row, dict):
            scores.append(0.0); continue
        scores.append(sum(1 for k in req if k in row) / len(req))
    frac = statistics.mean(scores)
    return (frac, f"{frac:.0%} of required keys present across {len(rows)} row(s)")


_ART_RE = re.compile(
    r"\b(?:article|art\.?|annex)\s*[\divxlc]+|\bEU[_ ]AI[_ ]ACT[_ ]ART[_ ]?\d+"
    r"|\b(?:GDPR|DORA|NIS2|CRA|CSRD|ISO[_ ]?42001)\b", re.I)


def citations_wellformed(text: str, task: dict) -> "tuple[float, str]":
    """Reward well-shaped regulatory citations; a compliance answer with zero
    article/framework references is ungrounded. Caps at 1.0 for >=2 refs."""
    if not task.get("expect_citations"):
        return (1.0, "citations not required")
    hits = _ART_RE.findall(text or "")
    n = len(hits)
    return (min(n / 2.0, 1.0), f"{n} regulatory reference(s)")


_REFUSAL_RE = re.compile(
    r"\b(i can'?t|i cannot|i'?m not able|i am unable|as an ai|i don'?t have|"
    r"unable to (?:help|assist)|consult a (?:professional|lawyer|expert)|"
    r"i'?m sorry,? but)\b", re.I)


def no_refusal(text: str, task: dict) -> "tuple[float, str]":
    t = (text or "").strip()
    if len(t) < 25:
        return (0.0, "empty/too-short answer")
    return (0.0, "answer is a refusal/deflection") if _REFUSAL_RE.search(t[:200]) else (1.0, "substantive answer")


_VERIFY_URL = "https://meok-attestation-api.vercel.app/verify/"


def attestation_verifies(text: str, task: dict) -> "tuple[float, str]":
    """If the reply references a MEOK cert id, hit the live verifier. The strongest
    possible external signal — a cryptographic check. Fail-open to neutral 0.5 if
    offline (don't punish for network, but don't reward an unverifiable claim)."""
    if not task.get("expect_attestation"):
        return (1.0, "attestation not required")
    m = re.search(r"MEOK-[A-Z0-9-]{8,}", text or "")
    if not m:
        return (0.0, "no cert id referenced")
    cert = m.group(0)
    try:
        with urllib.request.urlopen(_VERIFY_URL + cert, timeout=8) as r:
            ok = r.status == 200 and b"valid" in r.read().lower()
        return (1.0, f"{cert} verifies") if ok else (0.0, f"{cert} does NOT verify")
    except Exception:
        return (0.5, f"{cert} unverifiable (offline)")


# ── factual citation grounding (the market-ready truth gate) ────────────────
# Authoritative answer-key for high-value compliance topics. `citations_wellformed`
# only checks a citation is PRESENT; this checks it's the RIGHT one. Curated from the
# regulations themselves — the seed of what the MEOK compliance-MCP corpus serves at scale.
# topic -> (question-trigger regex, required reference regex, human label)
_FACTS = [
    ("ai_transparency",
     re.compile(r"transparen|watermark|ai[- ]?generated content|deepfake|chatbot disclos|synthetic (?:content|media)", re.I),
     re.compile(r"article\s*50|art\.?\s*50", re.I), "EU AI Act Article 50"),
    ("high_risk",
     re.compile(r"high[- ]?risk|credit[- ]?scor|annex\s*iii|biometric|recruitment ai", re.I),
     re.compile(r"annex\s*iii|article\s*6|art\.?\s*6", re.I), "EU AI Act Annex III / Art 6"),
    ("prohibited",
     re.compile(r"prohibit|unacceptable risk|banned (?:ai|practice)|social scoring", re.I),
     re.compile(r"article\s*5|art\.?\s*5", re.I), "EU AI Act Article 5"),
    ("logging",
     re.compile(r"record[- ]?keep|audit log|logging obligation|traceabilit", re.I),
     re.compile(r"article\s*12|art\.?\s*12", re.I), "EU AI Act Article 12"),
    ("human_oversight",
     re.compile(r"human oversight", re.I),
     re.compile(r"article\s*14|art\.?\s*14", re.I), "EU AI Act Article 14"),
]


def _art_ref_regex(article: str) -> "re.Pattern":
    """Build a 'does the answer cite this?' check from a KB article string like
    'Article 50' / 'Annex III (classified via Article 6)' / 'Articles 43 & 47-48'."""
    nums = re.findall(r"\d+", article)
    annex = re.findall(r"annex\s*([ivxlc]+)", article, re.I)
    alts = []
    for ninit in nums:
        alts.append(rf"art(?:icle)?\.?\s*{ninit}\b")
    for a in annex:
        alts.append(rf"annex\s*{a}\b")
    # framework name as a fallback citation (e.g. GDPR, DORA, NIS2, ISO 42001)
    fw = re.search(r"\b(GDPR|DORA|NIS ?2|ISO[/ ]?IEC? ?42001)\b", article, re.I)
    if fw:
        alts.append(re.escape(fw.group(0)).replace(r"\ ", r"\s?"))
    return re.compile("|".join(alts) if alts else r"$^", re.I)


def citation_correct(text: str, task: dict) -> "tuple[float, str]":
    """Truth gate: when the QUESTION is about a known compliance topic (from the MEOK
    regulation_kb — the single source of truth), does the ANSWER cite the CORRECT
    article? Neutral (1.0) for topics not in the KB — never penalise what we can't
    authoritatively check. Catches a confident-but-wrong "Article 19": structural vs
    FACTUAL verification, and where MEOK's regulation corpus is the moat."""
    q = (task.get("question") or task.get("prompt") or "")
    if not q:
        return (1.0, "no question to ground against")
    body = text or ""
    try:
        from .regulation_kb import KB
        relevant = [(v["article"], _art_ref_regex(v["article"]))
                    for v in KB.values() if re.search(v["triggers"], q, re.I)]
    except Exception:  # noqa: BLE001 — fall back to the legacy inline facts
        relevant = [(label, ref) for _, qre, ref, label in _FACTS if qre.search(q)]
    if not relevant:
        return (1.0, "topic not in answer-key (not penalised)")
    hits = [label for label, ref in relevant if ref.search(body)]
    frac = len(hits) / len(relevant)
    if frac == 1.0:
        return (1.0, f"correctly cites {', '.join(sorted(set(hits)))}")
    missing = [label for label, ref in relevant if not ref.search(body)]
    return (frac, f"WRONG/MISSING citation — expected {', '.join(sorted(set(missing)))}")


CHECKS: "dict[str, Verifier]" = {
    "json_valid": json_valid, "schema_keys": schema_keys,
    "citations_wellformed": citations_wellformed, "citation_correct": citation_correct,
    "no_refusal": no_refusal, "attestation_verifies": attestation_verifies,
}


def make_verifier(checks: "list[str] | dict[str, float]") -> Verifier:
    """Compose named checks into one verifier (weighted mean of scores)."""
    weights = {c: 1.0 for c in checks} if isinstance(checks, list) else dict(checks)

    def _v(text: str, task: dict) -> "tuple[float, str]":
        total, wsum, reasons = 0.0, 0.0, []
        for name, w in weights.items():
            fn = CHECKS.get(name)
            if not fn:
                continue
            s, why = fn(text, task)
            total += s * w; wsum += w
            reasons.append(f"{name}={s:.2f}({why})")
        score = total / wsum if wsum else 0.0
        return score, " · ".join(reasons)
    return _v


# ── verifier-gated best-of-N (test-time self-improvement) ───────────────────
def best_of_n(generate: "Callable[[int], str]", verify: Verifier, task: dict,
              n: int = 4) -> dict:
    """Generate N candidates, keep the verifier-best. Returns the winner + all
    scores. This is the half of self-improvement that provably helps TODAY —
    no training, just an external gate picking the best of diverse samples."""
    cands = []
    for i in range(max(1, n)):
        text = generate(i)
        score, reason = verify(text, task)
        cands.append({"i": i, "text": text, "score": round(score, 4), "reason": reason})
    cands.sort(key=lambda c: c["score"], reverse=True)
    best = cands[0]
    return {
        "best": best["text"], "best_score": best["score"], "best_reason": best["reason"],
        "n": n, "scores": [c["score"] for c in cands],
        "mean_score": round(statistics.mean(c["score"] for c in cands), 4),
        "lift_vs_first": round(best["score"] - cands[-1]["score"], 4) if len(cands) > 1 else 0.0,
        "candidates": cands,
    }


def prove_improvement(tasks: list, generate_for: "Callable[[dict, int], str]",
                      verify: Verifier, n: int = 4) -> dict:
    """HELD-OUT proof: for each task, compare best-of-1 (the first sample) against
    best-of-N (verifier-gated). Reports mean scores + the delta. This is the honest
    'did the loop make us better' measurement — an external metric on a set the
    selection never optimised against. Positive delta = real lift, not a self-report."""
    rows = []
    for t in tasks:
        cands = [generate_for(t, i) for i in range(n)]
        scored = [(verify(c, t)[0], c) for c in cands]
        bo1 = scored[0][0]                      # first sample = no selection
        boN = max(s for s, _ in scored)         # verifier-gated best
        rows.append({"task": t.get("name", t.get("prompt", "")[:40]),
                     "bo1": round(bo1, 3), "boN": round(boN, 3),
                     "delta": round(boN - bo1, 3)})
    mean_bo1 = statistics.mean(r["bo1"] for r in rows)
    mean_boN = statistics.mean(r["boN"] for r in rows)
    return {
        "n": n, "tasks": len(rows),
        "mean_best_of_1": round(mean_bo1, 4),
        "mean_best_of_N": round(mean_boN, 4),
        "mean_lift": round(mean_boN - mean_bo1, 4),
        "improved": mean_boN > mean_bo1,
        "rows": rows,
    }
