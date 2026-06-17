"""
MEOK ONE — OLM (Organic Learning Model): the live, in-context learning loop.

Per (user, character) we keep a small CARE-RANKED buffer of past turns. High-care
replies become "learn from these" few-shot examples; low-care become "avoid these".
Both are injected into the character's system prompt on the NEXT turn, so the model
improves by seeing its own best/worst IN CONTEXT — no retraining (ICRL).

The Maternal Covenant is the reward (`compute_care_reward`). Buffers persist per user
under data/olm/ — your AI's learning stays on your node ("stays yours forever").

Pure stdlib (MEOK ONE ships zero pip deps). Adapted from the SOV3 reference
sovereign-temple/icrl_self_improvement.py. See _TABS/OLM_SPEC_v0.1.md (v0.2).
"""
import json, os, re, time

_HERE = os.path.dirname(os.path.abspath(__file__))
_DIR = os.path.join(_HERE, "data", "olm")
MAX_EPISODES = 50      # keep the 50 highest-care turns per (user, character)
TOP_K = 3              # how many "best" examples to surface
_MIN_FOR_AVOID = 5     # only surface "avoid" examples once there's enough signal

CARE_WORDS = ["help", "understand", "care", "safe", "protect", "support",
              "listen", "here for you", "remember", "important to me", "proud of you",
              "you're not alone", "take your time", "i'm here"]
HARMFUL_WORDS = ["stupid", "worthless", "shut up", "don't care", "whatever",
                 "not my problem", "figure it out yourself", "idiot", "annoying"]


def compute_care_reward(text: str, emotion_confidence: float = 0.5) -> float:
    """The Maternal Covenant as a reward function — scores reply text by care alignment (0..1)."""
    lower = (text or "").lower()
    score = 0.5
    score += sum(0.05 for w in CARE_WORDS if w in lower)
    score -= sum(0.10 for w in HARMFUL_WORDS if w in lower)
    wc = len((text or "").split())
    if wc > 50:  score += 0.1
    if wc > 100: score += 0.1
    score += emotion_confidence * 0.1
    return max(0.0, min(1.0, round(score, 3)))


def _slug(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", str(s or "anon"))[:64] or "anon"

def _path(user_id: str, character_id: str) -> str:
    return os.path.join(_DIR, f"{_slug(user_id)}__{_slug(character_id)}.json")

def _load(user_id: str, character_id: str) -> list:
    try:
        with open(_path(user_id, character_id), "r", encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, list) else []
    except Exception:
        return []

def _save(user_id: str, character_id: str, episodes: list) -> None:
    try:
        os.makedirs(_DIR, exist_ok=True)
        p = _path(user_id, character_id)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(episodes, f, ensure_ascii=False)
        os.replace(tmp, p)   # atomic
    except Exception:
        pass


def record(user_id: str, character_id: str, query: str, response: str,
           care_flagged: bool = False, held: bool = False) -> dict:
    """Score the turn and add it to this (user, character)'s care-ranked buffer.
    A reply the sovereign gate flagged/held is forced LOW so it becomes an 'avoid' example."""
    reward = compute_care_reward(response)
    if held:         reward = min(reward, 0.05)
    elif care_flagged: reward = min(reward, 0.20)

    eps = _load(user_id, character_id)
    eps.append({"q": (query or "")[:500], "r": (response or "")[:1200],
                "care": reward, "ts": int(time.time())})
    if len(eps) > MAX_EPISODES:                       # keep the highest-care MAX_EPISODES
        eps.sort(key=lambda e: e.get("care", 0))
        eps = eps[-MAX_EPISODES:]
    _save(user_id, character_id, eps)
    return stats(user_id, character_id, _eps=eps)


def context(user_id: str, character_id: str) -> str:
    """Few-shot ICRL block to APPEND to the system prompt: best examples to emulate,
    worst to avoid. Returns '' until there's enough signal."""
    eps = _load(user_id, character_id)
    if len(eps) < 2:
        return ""
    # only surface replies ABOVE the caring baseline (0.5) as examples to emulate —
    # never hold up a cold/mediocre reply as "your best".
    best = [e for e in sorted(eps, key=lambda e: -e.get("care", 0)) if e.get("care", 0) >= 0.60][:TOP_K]
    if not best:
        return ""
    out = ["\n\n[OLM — you have learned from past conversations with THIS person.",
           "Echo the warmth + specificity of your best replies below; never the avoided ones.]",
           "\nYour best replies (emulate this care):"]
    for e in best:
        out.append(f'  · they said "{e["q"][:80]}" → you replied "{e["r"][:140]}"  (care {e["care"]:.2f})')
    if len(eps) >= _MIN_FOR_AVOID:
        worst = sorted(eps, key=lambda e: e.get("care", 0))[:1]
        if worst and worst[0].get("care", 1) < 0.4:
            out.append("\nAvoid replies like this (too cold / low-care):")
            out.append(f'  · "{worst[0]["r"][:140]}"  (care {worst[0]["care"]:.2f})')
    return "\n".join(out)


def stats(user_id: str, character_id: str, _eps=None) -> dict:
    eps = _eps if _eps is not None else _load(user_id, character_id)
    if not eps:
        return {"episodes": 0, "avg_care": 0.0, "improving": False}
    scores = [e.get("care", 0) for e in eps]
    recent = scores[-5:]
    first = scores[:5]
    return {
        "episodes": len(eps),
        "avg_care": round(sum(scores) / len(scores), 3),
        "best_care": round(max(scores), 3),
        "improving": (sum(recent) / len(recent)) > (sum(first) / len(first)) if len(scores) >= 6 else False,
    }
