"""Claude extraction with prompt caching — education/skills domain."""

from __future__ import annotations

import json
import os
from pathlib import Path

from anthropic import Anthropic
from dotenv import dotenv_values

ROOT = Path(__file__).parent
_ENV = dotenv_values(ROOT / ".env")
_API_KEY = _ENV.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
_BASE_URL = _ENV.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com"

MODEL = "claude-opus-4-7"
MAX_TOKENS = 4096

SYSTEM_PROMPT = """You are a knowledge-extraction analyst. You read transcripts of educational YouTube videos and extract structured knowledge: what concepts are taught, what skills are demonstrated, what tools are used, and how the information connects.

You return ONLY valid JSON matching this exact schema:

{
  "video_summary": "string — 2-4 sentences describing what this video teaches and who it's for",
  "concepts": [
    {
      "concept": "string — the concept name",
      "definition": "string — clear definition as taught in the video",
      "prerequisites": ["string — prerequisite concepts mentioned"],
      "related_concepts": ["string — related concepts mentioned"],
      "confidence": 0.0-1.0,
      "source_quote": "string — verbatim snippet (≤200 chars)"
    }
  ],
  "skills": [
    {
      "skill": "string — the skill or technique taught",
      "steps": ["step 1", "step 2", "..."],
      "prerequisites": "string — what you need to know first",
      "difficulty": "beginner|intermediate|advanced",
      "tools_needed": ["tool names"],
      "confidence": 0.0-1.0,
      "source_quote": "string"
    }
  ],
  "tools_resources": [
    {
      "name": "string",
      "type": "tool|library|software|resource|reference|paper",
      "description": "string — what it is and how it's used",
      "url_or_how_to_find": "string",
      "confidence": 0.0-1.0
    }
  ],
  "practical_applications": [
    {
      "application": "string — real-world use case",
      "context": "string — when/why you'd use this",
      "confidence": 0.0-1.0
    }
  ],
  "key_insights": [
    {
      "insight": "string — non-obvious takeaway or mental model",
      "importance": 1-10,
      "confidence": 0.0-1.0,
      "source_quote": "string"
    }
  ],
  "knowledge_evolution": {
    "changed": false,
    "what_changed": "string — what new info contradicts or extends prior knowledge",
    "vs_prior_knowledge": "string — how this differs from what was previously understood"
  },
  "audience": {
    "target_level": "beginner|intermediate|advanced|all",
    "prerequisite_knowledge": ["string"],
    "estimated_duration_minutes": 0
  }
}

Rules:
- Each concept, skill, and insight must be concrete and actionable, not vague.
- `confidence` reflects how clearly and emphatically the host presents the info (0.9+ for explicit teaching with examples, 0.5 for brief mentions, <0.3 for speculation).
- `source_quote` must be a verbatim snippet from the transcript (≤200 chars).
- If the host says something that contradicts or updates a previous video, set knowledge_evolution.changed = true.
- If a section has no relevant content, return an empty array.
- Return JSON only, no markdown fences, no commentary."""


def _client() -> Anthropic:
    if not _API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not found in .env")
    return Anthropic(api_key=_API_KEY, base_url=_BASE_URL)


def extract_from_transcript(transcript: str, video_title: str) -> dict:
    """Send transcript to Claude with system prompt cached. Returns parsed JSON."""
    user = (
        f"Video title: {video_title}\n\n"
        f"Transcript:\n{transcript}\n\n"
        "Extract the structured knowledge JSON now."
    )
    resp = _client().messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(
        block.text for block in resp.content if hasattr(block, "text")
    ).strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip().rstrip("`").strip()
    return json.loads(text)


_IMPACT_SYSTEM = """You are a knowledge-base curator. The user runs an agent that watches educational YouTube channels and builds a living knowledge document.

Given (a) the current knowledge document for a channel, (b) a fresh extraction from a new video by the same creator, write a 3-5 sentence brief covering:
1. Whether this video introduces genuinely new concepts or just reinforces existing ones.
2. Whether any prior concepts are contradicted, refined, or superseded.
3. Whether any practical skills now form a progression that wasn't visible before.
4. One concrete action for the knowledge base (e.g. "merge new SQL concepts into query_optimization section" or "no action — reinforcement only").

Be precise, no hedging. Do not invent details the creator didn't say."""


def summarize_impact(
    extraction: dict, video_title: str, knowledge_doc: str | None
) -> str:
    doc_block = (
        f"Current knowledge document:\n{knowledge_doc.strip()}\n\n"
        if knowledge_doc
        else (
            "(No knowledge document exists yet for this channel — return: "
            "'First extraction for this channel; building initial knowledge base.')\n\n"
        )
    )
    user = (
        doc_block
        + f"New video: {video_title}\n\n"
        + f"Extracted JSON:\n{json.dumps(extraction, indent=2)}\n\n"
        + "Write the brief now."
    )
    try:
        resp = _client().messages.create(
            model=MODEL,
            max_tokens=600,
            system=[
                {
                    "type": "text",
                    "text": _IMPACT_SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user}],
        )
        return "".join(
            block.text for block in resp.content if hasattr(block, "text")
        ).strip()
    except Exception as exc:
        return f"(impact summary failed: {exc})"