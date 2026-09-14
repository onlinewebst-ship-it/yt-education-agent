"""SQLite state + markdown IO — education/skills domain."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).parent
DB_PATH = ROOT / "state.db"
CHANNELS_DIR = ROOT / "channels"


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            video_id TEXT PRIMARY KEY,
            channel_id TEXT NOT NULL,
            handle TEXT NOT NULL,
            title TEXT NOT NULL,
            published_at TEXT NOT NULL,
            processed_at TEXT NOT NULL,
            extraction_json TEXT NOT NULL
        )
        """)
    return conn


def seen(video_id: str) -> bool:
    with _db() as conn:
        row = conn.execute(
            "SELECT 1 FROM videos WHERE video_id = ?", (video_id,)
        ).fetchone()
    return row is not None


def mark_seen(
    channel_id: str,
    handle: str,
    video_id: str,
    title: str,
    published_at: str,
    extraction: dict,
) -> None:
    with _db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO videos VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                video_id,
                channel_id,
                handle,
                title,
                published_at,
                datetime.now(timezone.utc).isoformat(),
                json.dumps(extraction),
            ),
        )


def latest_extractions(channel_id: str, limit: int = 5) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT video_id, title, published_at, extraction_json FROM videos "
            "WHERE channel_id = ? ORDER BY published_at DESC LIMIT ?",
            (channel_id, limit),
        ).fetchall()
    out = []
    for video_id, title, published_at, extraction_json in rows:
        out.append(
            {
                "video_id": video_id,
                "title": title,
                "published_at": published_at,
                "extraction": json.loads(extraction_json),
            }
        )
    return out


def channel_dir(handle: str) -> Path:
    d = CHANNELS_DIR / handle
    (d / "videos").mkdir(parents=True, exist_ok=True)
    return d


def write_video_md(
    handle: str, video_id: str, title: str, published_at: str, extraction: dict
) -> None:
    path = channel_dir(handle) / "videos" / f"{video_id}.md"
    lines = [
        f"# {title}",
        "",
        f"- Video: https://www.youtube.com/watch?v={video_id}",
        f"- Published: {published_at}",
        f"- Target audience: {extraction.get('audience', {}).get('target_level', '?')}",
        f"- Duration: {extraction.get('audience', {}).get('estimated_duration_minutes', '?')} min",
        "",
        "## Summary",
        extraction.get("video_summary", "").strip() or "_(none)_",
        "",
    ]

    # Concepts
    concepts = extraction.get("concepts") or []
    lines.append("## Concepts taught")
    if not concepts:
        lines.append("_(none)_")
    for item in concepts:
        conf = item.get("confidence", 0.0)
        name = item.get("concept", "?")
        defn = item.get("definition", "")
        prereqs = item.get("prerequisites") or []
        related = item.get("related_concepts") or []
        quote = (item.get("source_quote") or "").strip()
        lines.append(f"- ({conf:.2f}) **{name}**: {defn}")
        if prereqs:
            lines.append(f"  - Prerequisites: {', '.join(prereqs)}")
        if related:
            lines.append(f"  - Related: {', '.join(related)}")
        if quote:
            lines.append(f"  > {quote}")
    lines.append("")

    # Skills
    skills = extraction.get("skills") or []
    lines.append("## Skills taught")
    if not skills:
        lines.append("_(none)_")
    for item in skills:
        conf = item.get("confidence", 0.0)
        name = item.get("skill", "?")
        steps = item.get("steps") or []
        diff = item.get("difficulty", "?")
        prereqs = item.get("prerequisites", "")
        tools = item.get("tools_needed") or []
        quote = (item.get("source_quote") or "").strip()
        lines.append(f"- ({conf:.2f}) **{name}** (difficulty: {diff})")
        if prereqs:
            lines.append(f"  - Prerequisites: {prereqs}")
        if tools:
            lines.append(f"  - Tools: {', '.join(tools)}")
        if steps:
            lines.append(f"  - Steps:")
            for s in steps:
                lines.append(f"    {s}")
        if quote:
            lines.append(f"  > {quote}")
    lines.append("")

    # Tools & resources
    tools_res = extraction.get("tools_resources") or []
    lines.append("## Tools & resources mentioned")
    if not tools_res:
        lines.append("_(none)_")
    for item in tools_res:
        t = item.get("type", "tool")
        name = item.get("name", "?")
        desc = item.get("description", "")
        url = item.get("url_or_how_to_find", "")
        lines.append(f"- **{name}** ({t}): {desc}" + (f" — {url}" if url else ""))
    lines.append("")

    # Key insights
    insights = extraction.get("key_insights") or []
    lines.append("## Key insights")
    if not insights:
        lines.append("_(none)_")
    for item in insights:
        imp = item.get("importance", 5)
        insight = item.get("insight", "")
        conf = item.get("confidence", 0.0)
        quote = (item.get("source_quote") or "").strip()
        lines.append(f"- [重要度{imp}] ({conf:.2f}) {insight}")
        if quote:
            lines.append(f"  > {quote}")
    lines.append("")

    path.write_text("\n".join(lines) + "\n")


def write_knowledge_md(
    handle: str, title: str, knowledge: dict, sources: Iterable[dict]
) -> None:
    path = channel_dir(handle) / "knowledge.md"
    lines = [
        f"# {title} — Living Knowledge Document",
        "",
        f"_Last updated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}_",
        "",
        "## Overview",
        knowledge.get("knowledge_summary", "").strip() or "_(building — needs more videos)_",
        "",
    ]
    for section, key in [
        ("Core concepts", "concepts"),
        ("Skills inventory", "skills"),
        ("Practical applications", "applications"),
        ("Key insights", "insights"),
    ]:
        items = knowledge.get(key) or []
        lines.append(f"## {section}")
        if not items:
            lines.append("_(none yet)_")
        for item in items:
            lines.append(f"- ({item.get('effective_confidence', 0):.2f}) {item.get('text', '')}")
        lines.append("")
    lines.append("## Sources (rolling 5-video window)")
    for s in sources:
        lines.append(
            f"- [{s['title']}](https://www.youtube.com/watch?v={s['video_id']}) — {s['published_at']}"
        )
    path.write_text("\n".join(lines) + "\n")


def write_concepts_json(handle: str, concepts: dict) -> None:
    (channel_dir(handle) / "concepts.json").write_text(json.dumps(concepts, indent=2))


def read_concepts_json(handle: str) -> dict | None:
    p = channel_dir(handle) / "concepts.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())


def append_changelog(handle: str, entry: str) -> None:
    p = channel_dir(handle) / "changelog.md"
    header = "" if p.exists() else "# Knowledge evolution changelog\n\n"
    with p.open("a") as fh:
        fh.write(header + entry + "\n")