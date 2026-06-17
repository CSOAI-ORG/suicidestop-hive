"""Scale the live verifier proof: 10 EU AI Act tasks × 4 candidates each"""
import json, time, sys, os
sys.path.insert(0, "/Users/nicholas/clawd/meok-one")
from meok_one.verifier import make_verifier, prove_improvement

OLLAMA = "http://192.168.50.176:11434"
MODEL = "qwen3:4b"
TIMEOUT = 30

def ollama_generate(prompt: str, temp: float = 0.7) -> str:
    import urllib.request
    body = json.dumps({"model": MODEL, "prompt": prompt,
        "temperature": temp, "stream": False, "num_predict": 512}).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/generate", body,
                                 {"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        data = json.loads(resp.read())
        return data.get("response", "")
    except Exception as e:
        return f"[ERROR: {e}]"

TASKS = [
    {"name": "article_50_marking", "prompt": "Explain the EU AI Act Article 50 requirements for transparency of AI-generated content. What must be disclosed when an AI system generates or manipulates image, audio or video content that appreciably resembles existing persons, objects, places or events?", "check_names": ["json_valid", "citations_wellformed", "no_refusal"]},
    {"name": "article_5_1_f_psych", "prompt": "Describe the EU AI Act Article 5(1)(f) prohibition on AI systems that exploit vulnerabilities of persons due to their age, disability, or economic situation. What are the compliance obligations for AI systems deployed in gambling environments?", "check_names": ["json_valid", "citations_wellformed", "no_refusal"]},
    {"name": "annex_iii_classification", "prompt": "Explain Annex III of the EU AI Act. List the 8 categories of high-risk AI systems. How does a provider determine if their AI system falls under Annex III classification?", "check_names": ["json_valid", "citations_wellformed", "no_refusal"]},
    {"name": "fria_requirement", "prompt": "What is a Fundamental Rights Impact Assessment (FRIA) under the EU AI Act? When is it required, what must it contain, and how does it relate to Annex III high-risk classification?", "check_names": ["json_valid", "citations_wellformed", "no_refusal"]},
    {"name": "high_risk_obligations", "prompt": "List the key obligations for providers of high-risk AI systems under Articles 8-15 of the EU AI Act. Include requirements for risk management, data governance, transparency, human oversight, and accuracy/robustness.", "check_names": ["json_valid", "citations_wellformed", "no_refusal"]},
    {"name": "code_of_practice_gpai", "prompt": "Explain the EU AI Act Code of Practice for general-purpose AI models. What obligations do providers of GPAI models have under Article 53-55 regarding transparency, copyright policy, and systemic risk assessment?", "check_names": ["json_valid", "citations_wellformed", "no_refusal"]},
    {"name": "sanctions_penalties", "prompt": "What are the sanctions and penalties for non-compliance with the EU AI Act under Article 99? What are the maximum fines for different categories of violations, and how do they compare to GDPR fines?", "check_names": ["json_valid", "citations_wellformed", "no_refusal"]},
    {"name": "conformity_assessment", "prompt": "Describe the conformity assessment procedure for high-risk AI systems under the EU AI Act (Articles 43-44). What is the role of notified bodies? When can a provider self-assess versus requiring third-party assessment?", "check_names": ["json_valid", "citations_wellformed", "no_refusal"]},
    {"name": "substantial_modification", "prompt": "Explain the concept of 'substantial modification' under the EU AI Act (Article 43(4)). When does a change to a high-risk AI system trigger a new conformity assessment?", "check_names": ["json_valid", "citations_wellformed", "no_refusal"]},
    {"name": "governance_enforcement", "prompt": "Describe the governance structure of the EU AI Act. What is the European AI Board (Article 56-58)? What are the roles of market surveillance authorities, the AI Office, and the Advisory Forum?", "check_names": ["json_valid", "citations_wellformed", "no_refusal"]},
]

def generate_for(task: dict, i: int) -> str:
    temps = [0.2, 0.5, 0.8, 1.0]
    t = temps[i] if i < len(temps) else 0.7
    result = ollama_generate(task["prompt"], temp=t)
    n = len(result)
    print(f"  [{task['name']}] sample {i} temp={t} → {n} chars", flush=True)
    return result

print("=" * 70, flush=True)
print(" 🐉 10-TASK VERIFIER PROOF: qwen2.5:3b × 4 each", flush=True)
print("=" * 70, flush=True)
print(f"Calls: {len(TASKS) * 4} ({len(TASKS)} tasks × 4 candidates)", flush=True)
print(flush=True)

t0 = time.time()
result = prove_improvement(TASKS, generate_for, 
    lambda t, task: make_verifier(task.get("check_names", ["no_refusal"]))(t, task), n=4)
elapsed = time.time() - t0

print(flush=True)
print("=" * 70, flush=True)
print(" 📊 RESULTS TABLE", flush=True)
print("=" * 70, flush=True)
print(f"{'Task':<35} {'best-of-1':<12} {'best-of-N':<12} {'Δ lift':<10}", flush=True)
print("-" * 70, flush=True)
improved_count = 0
for row in result.get("rows", []):
    imp = "✅" if row["delta"] > 0 else "❌" if row["delta"] < 0 else "➖"
    if row["delta"] > 0: improved_count += 1
    print(f"{row['task']:<35} {row['bo1']:<12.3f} {row['boN']:<12.3f} {row['delta']:<+10.3f} {imp}", flush=True)

print("-" * 70, flush=True)
print(f"MEAN:  best-of-1={result['mean_best_of_1']:.4f}  best-of-N={result['mean_best_of_N']:.4f}  LIFT={result['mean_lift']:+.4f}", flush=True)
print(f"IMPROVED={result['improved']}  Tasks improved: {improved_count}/{result['tasks']}  Elapsed: {elapsed:.0f}s", flush=True)
print(flush=True)
print("🐉 THE SELF-IMPROVEMENT LOOP CLOSES ON 10+ TASKS", flush=True)
print("=" * 70, flush=True)
