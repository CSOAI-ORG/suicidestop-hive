"""
all_providers.py — MEOK ONE: a unified provider dispatcher that uses ALL
the API keys from the host's environment (including .env.local).

This is the canonical source for which models are available per provider
and which tier they map to (hot/warm/cold).

Providers:
  * OpenRouter (proxies DeepSeek, Kimi, Claude, Gemini, Step)
  * Direct Anthropic
  * Direct OpenAI
  * Direct Gemini
  * Direct Kimi / Moonshot
  * Direct StepFun
  * MEOK_VM_LLM (Ollama on GCP VM)
  * M2 local Ollama
  * Replicate
  * Tinker

Each entry maps: (provider, model, base_url, key_env, tier).
Tier is for memory tiering (hot/warm/cold) and cost optimisation.
"""
import os
import json
from typing import Any, Dict, List, Optional, Tuple

# Load .env.local explicitly so MEOK_VM_LLM etc. are present
def _load_env_local():
    env_file = os.path.expanduser("~/clawd/meok-one/.env.local")
    if os.path.exists(env_file):
        for line in open(env_file):
            if '=' in line and not line.strip().startswith('#'):
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))
_load_env_local()


PROVIDER_CONFIG: List[Tuple[str, str, str, str, str]] = [
    # --- OpenRouter (proxies many models) ---
    ("openrouter", "deepseek-v4-pro",     "https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY", "cold"),
    ("openrouter", "kimi-k2.7",           "https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY", "cold"),
    ("openrouter", "kimi-k2.7-code",      "https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY", "cold"),  # new: code-specialized K2.7, top-tier
    ("openrouter", "claude-opus-4.8",     "https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY", "cold"),
    ("openrouter", "gemini-2.5-pro",      "https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY", "cold"),
    ("openrouter", "step-2-16k",          "https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY", "cold"),
    ("openrouter", "qwen3:8b",            "https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY", "warm"), # 8B is warm-tier, not cold frontier
    # --- Direct Providers ---
    ("anthropic",  "claude-3-opus-20240229", "https://api.anthropic.com/v1/messages",        "ANTHROPIC_API_KEY", "cold"),
    ("openai",     "gpt-4o-mini",           "https://api.openai.com/v1/chat/completions",    "OPENAI_API_KEY",    "cold"),
    ("gemini",     "gemini-2.5-flash",      "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent", "GOOGLE_API_KEY", "warm"),
    ("gemini",     "gemini-2.5-pro",        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent", "GOOGLE_API_KEY", "cold"),
    ("kimi",       "kimi-k2-0711",          "https://api.moonshot.cn/v1/chat/completions",  "KIMI_API_KEY",      "cold"),
    ("moonshot",   "moonshot-v1-8k",        "https://api.moonshot.cn/v1/chat/completions",  "MOONSHOT_API_KEY",  "cold"), # Kimi/Moonshot might share API key
    ("stepfun",    "step-2-32k",            "https://api.stepfun.com/v1/chat/completions",  "STEPFUN_API_KEY",   "cold"),
    # --- MEOK VM Ollama on GCP ---
    ("ollama-vm",  "gemma3:4b",             os.environ.get("MEOK_VM_LLM", "http://localhost:11434") + "/api/chat", "MEOK_VM_KEY", "warm"), # GCP VM is warm-tier
    ("ollama-vm",  "moondream",             os.environ.get("MEOK_VM_LLM", "http://localhost:11434") + "/api/chat", "MEOK_VM_KEY", "warm"),
    # --- M2 Local Ollama ---
    ("ollama-local", "qwen3:0.6b",          "http://localhost:11434/api/chat",             "",                  "hot"),  # Hot tier, no API key needed
    ("ollama-local", "qwen3:4b",            "http://localhost:11434/api/chat",             "",                  "hot"),
    ("ollama-local", "qwen3:8b",            "http://localhost:11434/api/chat",             "",                  "warm"),
    # --- Replicate & Tinker ---
    ("replicate", "meta/llama-3-8b-instruct", "https://api.replicate.com/v1/predictions", "REPLICATE_API_TOKEN", "cold"),
    ("tinker", "tinker-pro", "https://api.tinker.ai/v1/chat/completions", "TINKER_API_KEY", "cold"),
]

def get_provider_config(provider: str, model: str) -> Optional[Dict[str, Any]]:
    for p, m, url, key_env, tier in PROVIDER_CONFIG:
        if p == provider and m == model:
            return {"provider": p, "model": m, "base_url": url, "key_env": key_env, "tier": tier}
    return None

def call_provider(provider: str, model: str, messages: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
    config = get_provider_config(provider, model)
    if not config:
        return {"error": f"Provider/model {provider}/{model} not found"}

    api_key = os.environ.get(config["key_env"]) if config["key_env"] else None
    if config["key_env"] and not api_key:
        return {"error": f"API key not set for {provider}/{model} (env var: {config['key_env']})"}

    headers = {"Content-Type": "application/json"}
    if api_key:
        if provider == "openrouter" or provider == "anthropic": # Anthropic uses this
            headers["x-api-key"] = api_key
        elif provider == "openai":
            headers["Authorization"] = f"Bearer {api_key}"
        elif provider == "kimi" or provider == "moonshot": # Kimi uses this
            headers["Authorization"] = f"Bearer {api_key}"
        elif provider == "stepfun":
            headers["Authorization"] = f"Bearer {api_key}"
        elif provider == "gemini": # Gemini uses query param, not header usually
            headers["x-goog-api-key"] = api_key # Fallback for some proxies
        elif provider == "ollama-vm":
            headers["X-MEOK-Key"] = api_key # MEOK VM has a custom proxy
        elif provider == "replicate":
            headers["Authorization"] = f"Token {api_key}"
        elif provider == "tinker":
            headers["X-Tinker-Api-Key"] = api_key

    data = {"model": model, "messages": messages, **kwargs}
    if provider == "gemini": # Gemini needs custom URL with key as query param for direct use
        url = config["base_url"] + f"?key={api_key}" if api_key else config["base_url"]
        req = urllib.request.Request(url, headers=headers, data=json.dumps(data).encode("utf-8"), method="POST")
    elif provider == "anthropic": # Anthropic needs messages format
        data = {"model": model, "messages": messages, "max_tokens": 4096, **kwargs}
        req = urllib.request.Request(config["base_url"], headers=headers, data=json.dumps(data).encode("utf-8"), method="POST")
    else:
        req = urllib.request.Request(config["base_url"], headers=headers, data=json.dumps(data).encode("utf-8"), method="POST")

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            res = json.load(r)
            if provider == "anthropic":
                return {"content": res.get("content", [{}])[0].get("text", ""), "raw": res}
            elif provider == "openai":
                return {"content": res.get("choices", [{}])[0].get("message", {}).get("content", ""), "raw": res}
            elif provider == "gemini":
                return {"content": res.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", ""), "raw": res}
            elif provider == "replicate":
                # Replicate API is async; this is for direct polling
                return {"content": "Replicate call initiated (async)", "raw": res}
            elif provider == "ollama-vm" or provider == "ollama-local":
                return {"content": res.get("message", {}).get("content", ""), "raw": res} # Ollama direct format
            else:
                return {"content": res.get("choices", [{}])[0].get("message", {}).get("content", ""), "raw": res}
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode()[:200], "status": e.code}
    except Exception as e:
        return {"error": str(e), "status": 500}


if __name__ == "__main__":
    # Example usage
    messages = [{"role": "user", "content": "What is the capital of France?"}]
    # Test OpenRouter (DeepSeek)
    print("\n--- Testing OpenRouter (DeepSeek) ---")
    res = call_provider("openrouter", "deepseek-v4-pro", messages)
    print(f"Result: {res.get("content")}")

    # Test Anthropic
    print("\n--- Testing Anthropic (Opus) ---")
    res = call_provider("anthropic", "claude-3-opus-20240229", messages)
    print(f"Result: {res.get("content")}")

    # Test MEOK VM Ollama (gemma3:4b)
    print("\n--- Testing MEOK VM Ollama (gemma3:4b) ---")
    res = call_provider("ollama-vm", "gemma3:4b", messages)
    print(f"Result: {res.get("content")}")

    # Test Local Ollama (qwen3:0.6b)
    print("\n--- Testing Local Ollama (qwen3:0.6b) ---")
    res = call_provider("ollama-local", "qwen3:0.6b", messages)
    print(f"Result: {res.get("content")}")
