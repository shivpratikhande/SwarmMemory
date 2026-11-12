"""Embedding generation.

Default provider is a deterministic local feature-hashing embedder (unigrams +
bigrams, signed hashing, sublinear tf, L2 normalised). It needs no network or
API key, so search results are reproducible in the demo. An OpenAI-compatible
`/embeddings` endpoint can be configured instead; its vectors are projected to
the column dimension.
"""
from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache

import httpx

from backend.config import get_settings

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "a an the of to for and or in on at by with from is are was were be been it this that as into "
    "without over under than then so we our you your i".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


def _bucket(feature: str, dim: int) -> tuple[int, float]:
    h = hashlib.blake2b(feature.encode(), digest_size=8).digest()
    idx = int.from_bytes(h[:4], "little") % dim
    sign = 1.0 if h[4] & 1 else -1.0
    return idx, sign


def local_embed(text: str, dim: int) -> list[float]:
    toks = tokenize(text)
    feats: dict[str, float] = {}
    for t in toks:
        feats[t] = feats.get(t, 0.0) + 1.0
        if len(t) > 4:  # light sub-word signal: prefixes catch reliable/reliability
            feats["p:" + t[:5]] = feats.get("p:" + t[:5], 0.0) + 0.5
    for a, b in zip(toks, toks[1:]):
        key = f"{a}_{b}"
        feats[key] = feats.get(key, 0.0) + 1.5
    vec = [0.0] * dim
    for f, tf in feats.items():
        i, s = _bucket(f, dim)
        vec[i] += s * (1.0 + math.log(tf))
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _project(v: list[float], dim: int) -> list[float]:
    if len(v) == dim:
        return v
    out = [0.0] * dim
    for i, x in enumerate(v):
        out[i % dim] += x
    n = math.sqrt(sum(x * x for x in out)) or 1.0
    return [x / n for x in out]


@lru_cache(maxsize=2048)
def _remote_embed(text: str) -> tuple[float, ...]:
    s = get_settings()
    r = httpx.post(
        s.embedding_api_url.rstrip("/") + "/embeddings",
        headers={"Authorization": f"Bearer {s.embedding_api_key}"},
        json={"model": s.embedding_model, "input": text},
        timeout=20,
    )
    r.raise_for_status()
    return tuple(r.json()["data"][0]["embedding"])


def embed(text: str) -> list[float]:
    s = get_settings()
    if s.embedding_provider == "openai" and s.embedding_api_url:
        return _project(list(_remote_embed(text)), s.embedding_dim)
    return local_embed(text, s.embedding_dim)


def capsule_text(title: str, description: str, category: str, tags: list[str], claim: dict) -> str:
    target = claim.get("target", "")
    return " ".join(
        [title, title, description, category.replace("_", " "), " ".join(tags), str(target), str(claim.get("metric", "")).replace("_", " ")]
    )
