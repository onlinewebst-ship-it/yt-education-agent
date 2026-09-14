"""SMTP email sender for per-video briefs — education/skills domain."""

from __future__ import annotations

import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).parent
_ENV = {
    **dotenv_values(ROOT / ".env"),
    **{k: v for k, v in os.environ.items() if k.startswith("SMTP_") or k == "EMAIL_TO"},
}


def _cfg() -> dict[str, str]:
    needed = ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO"]
    cfg = {k: _ENV.get(k, "") for k in needed}
    missing = [k for k, v in cfg.items() if not v]
    if missing:
        raise RuntimeError(f"missing SMTP env vars: {missing}")
    cfg["SMTP_PASSWORD"] = cfg["SMTP_PASSWORD"].replace(" ", "")
    return cfg


def _format_items(items: list[dict], top: int = 5) -> str:
    if not items:
        return "_(none)_"
    lines = []
    for r in items[:top]:
        text = r.get("text") or r.get("rule") or r.get("note") or r.get("concept") or r.get("skill") or ""
        conf = r.get("effective_confidence", r.get("confidence", 0.0))
        lines.append(f"  • ({conf:.2f}) {text}")
    return "\n".join(lines)


def _diff_sections(prior: list[dict], new: list[dict]) -> tuple[list[str], list[str]]:
    """Return (added_texts, removed_texts) by simple text equality."""
    prior_texts = {(r.get("text") or "").strip() for r in (prior or [])}
    new_texts = {(r.get("text") or "").strip() for r in (new or [])}
    added = sorted(new_texts - prior_texts)
    removed = sorted(prior_texts - new_texts)
    return [t for t in added if t], [t for t in removed if t]


def build_email_body(
    channel_title: str,
    channel_handle: str,
    video: dict,
    extraction: dict,
    prior_knowledge: dict | None,
    new_knowledge: dict,
    change_logged: bool,
    impact_paragraph: str,
) -> str:
    vid = video["video_id"]
    url = f"https://www.youtube.com/watch?v={vid}"
    summary = (extraction.get("video_summary") or "").strip() or "_(none)_"
    sections: list[str] = []
    sections.append(
        f"NEW VIDEO — {channel_title}\n{video['title']}\n{url}\nPublished: {video.get('published_at','?')}\n"
    )
    if change_logged:
        sections.append("⚡  KNOWLEDGE EVOLUTION DETECTED — see changelog.md\n")
    sections.append(f"IMPACT ON KNOWLEDGE BASE\n{impact_paragraph}\n")
    sections.append(f"WHAT THIS VIDEO TEACHES\n{summary}\n")
    sections.append(
        "KEY EXTRACTS FROM THIS VIDEO\n"
        f"Concepts:\n{_format_items(extraction.get('concepts', []), top=3)}\n\n"
        f"Skills:\n{_format_items(extraction.get('skills', []), top=3)}\n\n"
        f"Tools & resources:\n{_format_items(extraction.get('tools_resources', []), top=2)}\n\n"
        f"Key insights:\n{_format_items(extraction.get('key_insights', []), top=2)}\n"
    )
    if prior_knowledge is not None:
        added_concepts, removed_concepts = _diff_sections(
            prior_knowledge.get("concepts", []), new_knowledge.get("concepts", [])
        )
        added_skills, removed_skills = _diff_sections(
            prior_knowledge.get("skills", []), new_knowledge.get("skills", [])
        )
        diff_lines: list[str] = []
        if added_concepts:
            diff_lines.append("  + concept: " + "\n  + concept: ".join(added_concepts))
        if removed_concepts:
            diff_lines.append("  − concept: " + "\n  − concept: ".join(removed_concepts))
        if added_skills:
            diff_lines.append("  + skill: " + "\n  + skill: ".join(added_skills))
        if removed_skills:
            diff_lines.append("  − skill: " + "\n  − skill: ".join(removed_skills))
        sections.append(
            "WHAT CHANGED IN THE ROLLING KNOWLEDGE BASE\n"
            + (
                "\n".join(diff_lines)
                if diff_lines
                else "  (no knowledge-level changes; weighting may have shifted confidence)"
            )
            + "\n"
        )
    sections.append(
        "CURRENT KNOWLEDGE BASE\n"
        f"Summary: {(new_knowledge.get('knowledge_summary') or '').strip() or '(building)'}\n\n"
        f"Top concepts:\n{_format_items(new_knowledge.get('concepts', []), top=5)}\n\n"
        f"Top skills:\n{_format_items(new_knowledge.get('skills', []), top=3)}\n\n"
        f"Key insights:\n{_format_items(new_knowledge.get('insights', []), top=3)}\n"
    )
    sections.append(
        "FILES ON THE VPS\n"
        f"  channels/{channel_handle}/knowledge.md      — full living knowledge document\n"
        f"  channels/{channel_handle}/concepts.json      — structured concepts with confidence\n"
        f"  channels/{channel_handle}/changelog.md       — knowledge evolution log\n"
        f"  channels/{channel_handle}/videos/{vid}.md    — this video's full extract\n"
    )
    return "\n".join(sections)


def send_email(subject: str, body: str) -> None:
    cfg = _cfg()
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["SMTP_USER"]
    msg["To"] = cfg["EMAIL_TO"]
    msg.attach(MIMEText(body, "plain"))
    context = ssl.create_default_context()
    with smtplib.SMTP(cfg["SMTP_HOST"], int(cfg["SMTP_PORT"])) as server:
        server.starttls(context=context)
        server.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
        server.send_message(msg)