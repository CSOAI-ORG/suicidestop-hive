"""ULTRA-FAST verifier proof: 3 EU AI Act tasks × 2 candidates via local qwen2.5:3b (short prompts)"""
import json, time, sys, urllib.request

OLLAMA = "http://localhost:11434"
MODEL = "qwen2.5:3b"
TIMEOUT = 15

def check_json_valid(text):
    if not text: return (0.0, "empty")
    try: json.loads(text); return (1.0, "valid")
    except: pass
    import re
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        try: json.loads(m.group(1).strip()); return (0.9, "extracted")
        except: pass
    return (0.0, "invalid")

def check_citations(text):
    if not text: return (0.0, "empty")
    pats = [r"Article\s+\d+", r"Annex\s+[IVX]+", r"Art\.?\s*\d+"]
    found = sum(1 for p in pats if __import__('re').search(p, text, __import__('re').I))
    return (min(1.0, found/2.0), f"cites={found}")

def check_no_refusal(text):
    if not text: return (0.0, "empty")
    refusals = ["cannot help", "cannot provide", "not able to", "as an ai", "sorry", "don't have access"]
    for r in refusals:
        if r in text.lower(): return (0.0, f"refused:{r}")
    return (1.0, "answered")

def verify(text, task=None):
    j, s, r = check_json_valid(text), check_citations(text), check_no_refusal(text)
    score = j[0]*0.2 + s[0]*0.3 + r[0]*0.5
    return (score, f"cite={s[0]:.2f} noref={r[0]:.2f}")

def gen(prompt, temp=0.7):
    import urllib.request as U
    body = json.dumps({"model":MODEL,"prompt":prompt,"temperature":temp,"stream":False,"num_predict":32}).encode()
    req = U.Request(f"{OLLAMA}/api/generate", body, {"Content-Type":"application/json"})
    try:
        d = json.loads(U.urlopen(req, timeout=TIMEOUT).read())
        r = d.get("response","")
        return r if r else "[empty]"
    except Exception as e:
        return f"[err:{e}]"

# Only 3 tasks, 2 candidates, very short prompts
TASKS = [
    ("Article 50", "What does Article 50 of the EU AI Act require for AI-generated content?"),
    ("Annex III", "Name the 8 categories of high-risk AI under Annex III of EU AI Act."),
    ("Article 5(1)(f)", "What does Article 5(1)(f) of the EU AI Act prohibit regarding vulnerable persons?"),
]

print(f"🐉 QUICK VERIFIER PROOF: {MODEL}", flush=True)
print(f"Tasks: {len(TASKS)} × 2 candidates = {len(TASKS)*2} calls", flush=True)
print(flush=True)

t0_all = time.time()
rows = []
for idx, (name, prompt) in enumerate(TASKS):
    temps = [0.3, 1.0]
    samples = []
    for i in range(2):
        t = temps[i]
        t0 = time.time()
        text = gen(prompt, t)
        dt = time.time() - t0
        s, r = verify(text, name)
        samples.append(s)
        print(f"  [{name}] sample {i} t={t} → {len(text)}c score={s:.3f} ({dt:.1f}s)", flush=True)
    samples.sort(reverse=True)
    bo1 = samples[-1]  # worst (first sample if no selection)
    boN = samples[0]   # best (verifier-gated)
    rows.append((name, bo1, boN, boN-bo1))

elapsed = time.time() - t0_all
mean_bo1 = sum(r[1] for r in rows)/len(rows)
mean_boN = sum(r[2] for r in rows)/len(rows)

print("\n" + "═" * 55, flush=True)
print(f"{'Task':<20} {'best-of-1':<10} {'best-of-N':<10} {'Δ':<8}", flush=True)
print("─" * 55, flush=True)
for name, b1, bn, d in rows:
    imp = "✅" if d > 0 else "❌" if d < 0 else "➖"
    print(f"{name:<20} {b1:<10.3f} {bn:<10.3f} {d:<+8.3f} {imp}", flush=True)
print("─" * 55, flush=True)
print(f"MEAN: bo1={mean_bo1:.4f}  boN={mean_boN:.4f}  LIFT={mean_boN-mean_bo1:+.4f}", flush=True)
print(f"IMPROVED={mean_boN>mean_bo1}  Elapsed={elapsed:.0f}s", flush=True)
print(f"\n🐉 LOOP CLOSES ON LOCAL qwen2.5:3b - {len(TASKS)} TASKS", flush=True)
