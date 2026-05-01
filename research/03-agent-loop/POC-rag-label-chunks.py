"""
POC: chunk an openFDA label JSON and BM25-lite keyword retrieval.

Run: python research/03-agent-loop/POC-rag-label-chunks.py

Demonstrates:
- Section-aware chunking (7 relevant sections)
- 800-token max per chunk
- Keyword overlap retrieval (no embeddings needed for v0.1)
- source_url on every chunk for citation
"""

import httpx
import math
import re
from collections import Counter

LABEL_BASE = "https://api.fda.gov/drug/label.json"

KEEP_SECTIONS = [
    "indications_and_usage",
    "dosage_and_administration",
    "contraindications",
    "warnings",
    "boxed_warning",
    "drug_interactions",
    "clinical_pharmacology",
]


def fetch_label(rxcui: str) -> dict | None:
    resp = httpx.get(LABEL_BASE, params={"search": f"openfda.rxcui:{rxcui}", "limit": 1}, timeout=15)
    if resp.status_code != 200:
        return None
    results = resp.json().get("results", [])
    return results[0] if results else None


def chunk_label(label: dict, rxcui: str, max_tokens: int = 800) -> list[dict]:
    """Split each relevant section into ~800-token chunks."""
    chunks = []
    source_url = f"{LABEL_BASE}?search=openfda.rxcui:{rxcui}"
    for section in KEEP_SECTIONS:
        val = label.get(section)
        if not val:
            continue
        text = "\n".join(val) if isinstance(val, list) else str(val)
        # Paragraph-aware split
        paragraphs = re.split(r"\n\s*\n", text)
        current, current_tokens = [], 0
        for p in paragraphs:
            p_tokens = len(p) // 4
            if current_tokens + p_tokens > max_tokens and current:
                chunks.append({
                    "section": section,
                    "text": "\n\n".join(current),
                    "source_url": source_url,
                    "tokens": current_tokens,
                })
                current, current_tokens = [p], p_tokens
            else:
                current.append(p)
                current_tokens += p_tokens
        if current:
            chunks.append({
                "section": section,
                "text": "\n\n".join(current),
                "source_url": source_url,
                "tokens": current_tokens,
            })
    return chunks


def tokenize(s: str) -> list[str]:
    return re.findall(r"[a-z]+", s.lower())


def bm25_lite_score(chunk_terms: Counter, query_terms: list[str], avg_doc_len: float, doc_len: int, k1=1.5, b=0.75) -> float:
    """Simplified BM25 without IDF (single-corpus = same docs)."""
    score = 0.0
    for term in query_terms:
        tf = chunk_terms.get(term, 0)
        if tf == 0:
            continue
        norm = (1 - b) + b * (doc_len / avg_doc_len if avg_doc_len else 1)
        score += (tf * (k1 + 1)) / (tf + k1 * norm)
    return score


def retrieve(chunks: list[dict], query: str, k: int = 3) -> list[dict]:
    if not chunks:
        return []
    query_terms = tokenize(query)
    chunk_terms = [Counter(tokenize(c["text"])) for c in chunks]
    doc_lens = [sum(ct.values()) for ct in chunk_terms]
    avg = sum(doc_lens) / len(doc_lens)

    scored = []
    for c, ct, dl in zip(chunks, chunk_terms, doc_lens):
        s = bm25_lite_score(ct, query_terms, avg, dl)
        scored.append((s, c))
    scored.sort(key=lambda x: -x[0])
    return [c for s, c in scored[:k] if s > 0]


if __name__ == "__main__":
    rxcui = "2555"  # cisplatin
    label = fetch_label(rxcui)
    if not label:
        print(f"No label for RxCUI {rxcui}")
        exit(1)

    chunks = chunk_label(label, rxcui)
    print(f"Total chunks: {len(chunks)}")
    print(f"Section distribution: {Counter(c['section'] for c in chunks)}")
    print(f"Total tokens across chunks: {sum(c['tokens'] for c in chunks)}\n")

    query = "oncology indications dose adjustment renal"
    top = retrieve(chunks, query, k=3)
    print(f"=== Top 3 chunks for query: '{query}' ===\n")
    for i, c in enumerate(top, 1):
        print(f"--- Rank {i} | section={c['section']} | tokens={c['tokens']} ---")
        print(c["text"][:300].replace("\n", " "))
        print(f"  [cite: {c['source_url']}]")
        print()
