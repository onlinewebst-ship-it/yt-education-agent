"""Detect knowledge evolution between consecutive video extractions."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from store import append_changelog, read_concepts_json
from weighting import _embed

SUMMARY_DRIFT_THRESHOLD = 0.35
CONTRADICTION_CONFIDENCE = 0.6


def _semantic_distance(a: str, b: str) -> float:
    if not a.strip() or not b.strip():
        return 0.0
    embs = _embed([a, b])
    sim = float(np.dot(embs[0], embs[1]))
    return 1.0 - sim


def detect_and_log(
    handle: str, video_id: str, video_title: str, new_extraction: dict
) -> bool:
    prior = read_concepts_json(handle)
    triggers: list[str] = []
    if prior:
        prior_summary = prior.get("knowledge_summary", "")
        new_summary = new_extraction.get("video_summary", "")
        if _semantic_distance(prior_summary, new_summary) > SUMMARY_DRIFT_THRESHOLD:
            triggers.append("Knowledge summary drifted significantly from prior state.")

        # Check for contradictions in high-confidence prior concepts vs new concepts
        prior_concepts = [
            c["text"]
            for c in prior.get("concepts", [])
            if c.get("effective_confidence", 0) >= CONTRADICTION_CONFIDENCE
        ]
        new_concepts = [
            c.get("concept", "")
            for c in new_extraction.get("concepts", [])
        ]
        if prior_concepts and new_concepts:
            embs_prior = _embed(prior_concepts)
            embs_new = _embed(new_concepts)
            for i, e_new in enumerate(embs_new):
                for j, e_prior in enumerate(embs_prior):
                    sim = float(np.dot(e_new, e_prior))
                    if 0.55 < sim < 0.78:
                        triggers.append(
                            f'Possible contradiction: new concept "{new_concepts[i]}" vs prior "{prior_concepts[j]}"'
                        )
                        break

        # Check for skill progression signals
        prior_skills = [
            s["text"]
            for s in prior.get("skills", [])
            if s.get("effective_confidence", 0) >= CONTRADICTION_CONFIDENCE
        ]
        new_skills = [
            s.get("skill", "")
            for s in new_extraction.get("skills", [])
        ]
        if prior_skills and new_skills:
            embs_prior = _embed(prior_skills)
            embs_new = _embed(new_skills)
            for i, e_new in enumerate(embs_new):
                for j, e_prior in enumerate(embs_prior):
                    sim = float(np.dot(e_new, e_prior))
                    if 0.55 < sim < 0.78:
                        triggers.append(
                            f'Possible skill contradiction: new "{new_skills[i]}" vs prior "{prior_skills[j]}"'
                        )
                        break

    evolution = new_extraction.get("knowledge_evolution") or {}
    if evolution.get("changed"):
        triggers.append(
            f"Creator explicitly noted a knowledge update: {evolution.get('what_changed', '')} "
            f"(vs {evolution.get('vs_prior_knowledge', '')})"
        )
    if not triggers:
        return False
    today = datetime.now(timezone.utc).date().isoformat()
    quote = ""
    for src in (new_extraction.get("concepts") or []) + (
        new_extraction.get("key_insights") or []
    ):
        if src.get("source_quote"):
            quote = src["source_quote"]
            break
    entry_lines = [
        f"## {today} — {video_title} ({video_id})",
    ]
    for t in triggers:
        entry_lines.append(f"- {t}")
    if quote:
        entry_lines.append(f'- Triggering quote: "{quote}"')
    append_changelog(handle, "\n".join(entry_lines))
    return True