"""LLM extraction via OpenAI-compatible API (DeepSeek / OpenRouter) — education/skills domain."""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import dotenv_values
import httpx

ROOT = Path(__file__).parent
_ENV = dotenv_values(ROOT / ".env")
_API_KEY = (
    _ENV.get("OPENAI_API_KEY")
    or os.environ.get("OPENAI_API_KEY")
    or _ENV.get("LLM_API_KEY")
    or os.environ.get("LLM_API_KEY")
)
_BASE_URL = (
    _ENV.get("OPENAI_BASE_URL")
    or os.environ.get("OPENAI_BASE_URL")
    or _ENV.get("LLM_BASE_URL")
    or os.environ.get("LLM_BASE_URL")
    or "https://openrouter.ai/api/v1"
)
_MODEL = (
    _ENV.get("EXTRACTION_MODEL")
    or os.environ.get("EXTRACTION_MODEL")
    or "deepseek/deepseek-v4-flash"
)
MAX_TOKENS = 4096
CHAT_ENDPOINT = "chat/completions"
# DeepSeek models consume reasoning tokens separately from output tokens.
# We request extra headroom to ensure complete JSON output.
_EXTRA_REASONING_TOKENS = 8192

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


def _client() -> httpx.Client:
    if not _API_KEY:
        raise RuntimeError("No API key found. Set OPENAI_API_KEY or LLM_API_KEY in .env")
    return httpx.Client(
        base_url=_BASE_URL,
        headers={
            "Authorization": f"Bearer {_API_KEY}",
            "Content-Type": "application/json",
        },
        timeout=120.0,
    )


def _llm_call(messages: list[dict], max_tokens: int = MAX_TOKENS) -> str:
    """Make an OpenAI-compatible chat completion call via httpx.
    Uses extra-large max_tokens to accommodate DeepSeek's reasoning overhead."""
    payload = {
        "model": _MODEL,
        "messages": messages,
        "max_tokens": max_tokens + _EXTRA_REASONING_TOKENS,  # headroom for reasoning
        "stream": False,
    }
    with _client() as client:
        resp = client.post(f"/{CHAT_ENDPOINT}", json=payload)
        resp.raise_for_status()
        data = resp.json()
    text = data["choices"][0]["message"]["content"] or ""
    return text


def _extract_json(text: str) -> dict:
    """Strip markdown fences and parse JSON from LLM response.
    Falls back to repairing truncated JSON if available."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip().rstrip("`").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try repairing truncated JSON (unterminated strings, missing brackets)
        repaired = _repair_truncated_json(cleaned)
        if repaired:
            return json.loads(repaired)
        raise


def _repair_truncated_json(text: str) -> str:
    """Attempt to repair a JSON string that was truncated mid-output.
    Closes unterminated strings, arrays, and objects."""
    # Close unterminated strings
    result = []
    in_string = False
    escape = False
    for ch in text:
        if escape:
            escape = False
            result.append(ch)
            continue
        if ch == "\\" and in_string:
            escape = True
            result.append(ch)
            continue
        if ch == '"' and in_string:
            in_string = False
            result.append(ch)
            continue
        if ch == '"' and not in_string:
            in_string = True
            result.append(ch)
            continue
        result.append(ch)
    if in_string:
        result.append('"')
    
    repaired = "".join(result)
    
    # Balance brackets
    stack = []
    pairs = {"{": "}", "[": "]", '"': '"'}
    for ch in repaired:
        if ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack and stack[-1] == {"}": "{", "]": "["}[ch]:
                stack.pop()
    # Close unclosed brackets
    for opener in reversed(stack):
        repaired += pairs[opener]
    
    return repaired


def extract_from_transcript(transcript: str, video_title: str) -> dict:
    """Send transcript to LLM (DeepSeek/OpenRouter). Returns parsed JSON."""
    user = (
        f"Video title: {video_title}\n\n"
        f"Transcript:\n{transcript}\n\n"
        "Extract the structured knowledge JSON now."
    )
    text = _llm_call([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ])
    return _extract_json(text)


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
        return _llm_call([
            {"role": "system", "content": _IMPACT_SYSTEM},
            {"role": "user", "content": user},
        ], max_tokens=600)
    except Exception as exc:
        return f"(impact summary failed: {exc})"