"""Recency weighting + similarity grouping for rolling 5-video window."""

from __future__ import annotations

from functools import lru_cache
from typing import Iterable

import numpy as np

WEIGHTS = [1.00, 0.70, 0.50, 0.35, 0.25]
SIMILARITY_THRESHOLD = 0.82
MIN_EFFECTIVE_CONFIDENCE = 0.30


@lru_cache(maxsize=1)
def _model():
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer("all-MiniLM-L6-v2")
    except (ImportError, OSError):
        return None


def _embed(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.zeros((0, 384))
    m = _model()
    if m is None:
        return np.zeros((len(texts), 384))
    return m.encode(texts, normalize_embeddings=True, show_progress_bar=False)


def _group(items: list[dict], text_key: str) -> list[list[dict]]:
    if not items:
        return []
    embs = _embed([it[text_key] for it in items])
    groups: list[list[int]] = []
    group_centroids: list[np.ndarray] = []
    for i, emb in enumerate(embs):
        placed = False
        for gi, centroid in enumerate(group_centroids):
            if float(np.dot(emb, centroid)) >= SIMILARITY_THRESHOLD:
                groups[gi].append(i)
                members = np.stack([embs[j] for j in groups[gi]])
                group_centroids[gi] = members.mean(axis=0)
                group_centroids[gi] /= np.linalg.norm(group_centroids[gi]) + 1e-9
                placed = True
                break
        if not placed:
            groups.append([i])
            group_centroids.append(emb)
    return [[items[i] for i in g] for g in groups]


def _weight_for_index(idx: int) -> float:
    return WEIGHTS[idx] if idx < len(WEIGHTS) else 0.0


def _rebuild_section(section_per_video: list[list[dict]], text_key: str) -> list[dict]:
    """section_per_video[0] is the most recent video's items."""
    flat: list[dict] = []
    for video_idx, items in enumerate(section_per_video):
        weight = _weight_for_index(video_idx)
        for item in items or []:
            flat.append(
                {
                    "text": item.get(text_key, "").strip(),
                    "raw_confidence": float(item.get("confidence", 0.5)),
                    "weight": weight,
                    "source_quote": item.get("source_quote", ""),
                    "video_idx": video_idx,
                }
            )
    flat = [f for f in flat if f["text"]]
    if not flat:
        return []
    grouped = _group(flat, "text")
    out = []
    for group in grouped:
        weights = [g["weight"] for g in group]
        confs = [g["raw_confidence"] * g["weight"] for g in group]
        eff = sum(confs) / max(sum(weights), 1e-9)
        if eff < MIN_EFFECTIVE_CONFIDENCE:
            continue
        canonical = max(group, key=lambda g: g["raw_confidence"] * g["weight"])
        out.append(
            {
                "text": canonical["text"],
                "effective_confidence": round(eff, 3),
                "source_quote": canonical["source_quote"],
                "appears_in": sorted({g["video_idx"] for g in group}),
            }
        )
    out.sort(key=lambda r: r["effective_confidence"], reverse=True)
    return out


def _pick_summary(extractions: list[dict]) -> str:
    """Headline summary for the document.

    Prefer the newest video that actually yielded teaching content. A degenerate
    upload (short, music-only, no concepts/skills/insights) would otherwise
    overwrite the whole document's overview with "this teaches nothing".
    """
    for e in extractions:
        summary = (e.get("video_summary") or "").strip()
        if summary and any(
            e.get(k) for k in ("concepts", "skills", "tools_resources", "key_insights")
        ):
            return summary
    for e in extractions:
        summary = (e.get("video_summary") or "").strip()
        if summary:
            return summary
    return ""


def rebuild(extractions_newest_first: Iterable[dict]) -> dict:
    """Build a unified knowledge dict from a rolling window of extractions (newest first)."""
    extractions = list(extractions_newest_first)[: len(WEIGHTS)]
    return {
        "knowledge_summary": _pick_summary(extractions),
        "concepts": _rebuild_section(
            [e.get("concepts") for e in extractions], "concept"
        ),
        "skills": _rebuild_section(
            [e.get("skills") for e in extractions], "skill"
        ),
        "applications": _rebuild_section(
            [e.get("practical_applications") for e in extractions], "application"
        ),
        "insights": _rebuild_section(
            [e.get("key_insights") for e in extractions], "insight"
        ),
    }
