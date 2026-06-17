"""
MEOK ONE — FLYWHEEL INGEST: hives consume folders → embeddings → training corpus.

The data flywheel engine (2026-06-16). Nick: "hives can consume all our folders and
my research files, train neural nets and RL, then eat other data too." This is step 1:
turn any folder of docs into an embedded, queryable, training-ready corpus — on the VM,
with the VM's own models (nomic-embed-text for embeddings, no cloud).

Pipeline:
  walk(folder) → chunk text files → embed each chunk (Ollama nomic-embed-text)
  → write JSONL rows {source, chunk, vector, ts} to a corpus file
  → (downstream) load into pgvector for retrieval, or use as SFT/RL training data.

Free + local: embeddings via Ollama on the VM. No API keys, nothing to suspend.

    ingest(folder, out=...) -> {files, chunks, embedded, corpus_path}
    search(query, corpus, k) -> top-k chunks (cosine) — proves the corpus is queryable
"""
from __future__ import annotations

import json
import math
import os
import time
import urllib.request
from pathlib import Path

_OLLAMA = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
_EMBED_MODEL = os.environ.get("MEOK_EMBED_MODEL", "nomic-embed-text")
_TEXT_EXT = {".md", ".txt", ".py", ".json", ".yaml", ".yml", ".csv", ".html", ".rst"}
_CHUNK = int(os.environ.get("MEOK_CHUNK_CHARS", "1200"))
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".next", "dist",
              ".cache", "lost+found"}


def _embed(text: str, timeout: int = 30) -> "list | None":
    try:
        body = json.dumps({"model": _EMBED_MODEL, "prompt": text[:8000]}).encode()
        req = urllib.request.Request(_OLLAMA + "/api/embeddings", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode()).get("embedding")
    except Exception:  # noqa: BLE001
        return None


def _chunks(text: str, size: int = _CHUNK):
    text = text.strip()
    for i in range(0, len(text), size):
        c = text[i:i + size].strip()
        if len(c) > 40:
            yield c


def ingest(folder: str, out: "str | None" = None, max_files: int = 5000,
           max_mb: float = 5.0) -> dict:
    """Embed every text file under `folder` into a JSONL corpus. Skips binaries,
    caches, and oversized files. Returns stats + the corpus path."""
    root = Path(folder).expanduser()
    out = out or str(root / "_flywheel_corpus.jsonl")
    files = chunks = embedded = 0
    t0 = time.time()
    with open(out, "w", encoding="utf-8") as fh:
        for p in root.rglob("*"):
            if files >= max_files:
                break
            if any(d in p.parts for d in _SKIP_DIRS):
                continue
            if not p.is_file() or p.suffix.lower() not in _TEXT_EXT:
                continue
            try:
                if p.stat().st_size > max_mb * 1_000_000:
                    continue
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:  # noqa: BLE001
                continue
            files += 1
            for ch in _chunks(text):
                chunks += 1
                vec = _embed(ch)
                if vec:
                    embedded += 1
                    fh.write(json.dumps({"source": str(p), "chunk": ch, "vector": vec}) + "\n")
    return {"folder": str(root), "files": files, "chunks": chunks, "embedded": embedded,
            "corpus_path": out, "embed_model": _EMBED_MODEL,
            "wall_s": round(time.time() - t0, 1)}


def _cos(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def search(query: str, corpus: str, k: int = 5) -> list:
    """Top-k chunks by cosine similarity — proves the corpus is queryable (the
    retrieval half of the flywheel; pgvector does this at scale)."""
    qv = _embed(query)
    if not qv:
        return []
    rows = []
    with open(corpus, encoding="utf-8") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            rows.append((_cos(qv, d["vector"]), d["source"], d["chunk"][:200]))
    rows.sort(reverse=True)
    return [{"score": round(s, 3), "source": src, "preview": ch} for s, src, ch in rows[:k]]


def _cli():
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == "search":
        print(json.dumps(search(sys.argv[2], sys.argv[3] if len(sys.argv) > 3
                                 else "_flywheel_corpus.jsonl"), indent=2)); return
    folder = sys.argv[1] if len(sys.argv) > 1 else "."
    print(json.dumps(ingest(folder), indent=2, default=str))


if __name__ == "__main__":
    _cli()
