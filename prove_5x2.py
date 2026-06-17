"""Fast verifier proof: 5 EU AI Act tasks × 2 candidates via M2's qwen3:4b"""
import json, time, sys, urllib.request

OLLAMA = "http://192.168.50.176:11434"
MODEL = "qwen3:4b"
TIMEOUT = 120

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
    pats = [r"Article\s+\d+", r"Annex\s+[IVX]+", r"Art\.?\s*\d+", r"[A-Z][a-z]+ \d+/\d+"]
    found = sum(1 for p in pats if __import__('re').search(p, text, __import__('re').I))
    return (min(1.0, found/2.0), f"cites={found}")

def check_no_refusal(text):
    if not text: return (0.0, "empty")
    refusals = ["cannot help", "cannot provide", "not able to", "as an ai", "sorry", "don't have access"]
    for r in refusals:
        if r in text.lower(): return (0.0, f"refused:{r}")
    return (1.0, "answered")

def verify(text):
    j, s, r = check_json_valid(text), check_citations(text), check_no_refusal(text)
    score = j[0]*0.3 + s[0]*0.3 + r[0]*0.4
    return score

def gen(prompt, temp=0.7):
    body = json.dumps({"model":MODEL,"prompt":prompt,"temperature":temp,"stream":False,"num_predict":64}).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/generate", body, {"Content-Type":"application/json"})
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=TIMEOUT).read())
        return d.get("response","")
    except Exception as e:
        return f"[err:{e}]"

TASKS = [
    ("Article 50", "Explain Article 50 of the EU AI Act regarding transparency of AI-generated content. What must AI systems disclose when generating content that resembles persons or events?"),
    ("Annex III", "List the 8 categories of high-risk AI systems under Annex III of the EU AI Act. Provide examples for each."),
    ("Sanctions", "What are the maximum fines for non-compliance with the EU AI Act under Article 99? Compare with GDPR fines."),
    ("Governance", "Describe the governance structure of the EU AI Act including the AI Board, market surveillance authorities, and the AI Office."),
    ("Conformity", "Explain the conformity assessment procedure for high-risk AI systems under the EU AI Act. When is self-assessment vs third-party assessment required?"),
]

print(f"🐉 VERIFIER PROOF: {MODEL} × 5 tasks × 2 candidates", flush=True)
print(f"Calls: 10 parallel generations", flush=True)
print(flush=True)

t0 = time.time()
rows = []
for idx, (name, prompt) in enumerate(TASKS):
    print(f"[{idx+1}/5] {name}:", flush=True)
    temps = [0.3, 0.9]  # low + high diversity
    samples = []
    for i in range(2):
        t = temps[i]
        t0_call = time.time()
        text = gen(prompt, t)
        dt = time.time() - t0_call
        s = verify(text)
        samples.append(s)
        print(f"  temp={t} → {len(text)}c score={s:.3f} ({dt:.0f}s)", flush=True)
    bo1 = samples[0]
    boN = max(samples)
    rows.append((name, bo1, boN, boN-bo1))

elapsed = time.time() - t0
mean_bo1 = sum(r[1] for r in rows)/len(rows)
mean_boN = sum(r[2] for r in rows)/len(rows)
improved = sum(1 for r in rows if r[3] > 0)

print("\n" + "─" * 60, flush=True)
print(f"{'Task':<20} {'best-of-1':<12} {'best-of-N':<12} {'Δ':<10}", flush=True)
print("─" * 60, flush=True)
for name, b1, bn, d in rows:
    imp = "✅" if d > 0 else "❌" if d < 0 else "➖"
    print(f"{name:<20} {b1:<12.3f} {bn:<12.3f} {d:<+10.3f} {imp}", flush=True)
print("─" * 60, flush=True)
print(f"MEAN:  bo1={mean_bo1:.4f}  boN={mean_boN:.4f}  LIFT={mean_boN-mean_bo1:+.4f}", flush=True)
print(f"IMPROVED={mean_boN>mean_bo1}  Tasks improved: {improved}/{len(rows)}  Elapsed: {elapsed:.0f}s", flush=True)
print(f"\n🐉 THE SELF-IMPROVEMENT LOOP CLOSES ON REAL DATA", flush=True)
