"""Main ingest pipeline. Run with --once for a single pass."""

from __future__ import annotations

import argparse
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml
from dotenv import dotenv_values
from googleapiclient.discovery import build

from auth import load_cached_credentials
from change_detect import detect_and_log
from extract import extract_from_transcript, summarize_impact
from notify import build_email_body, send_email
from transcript import fetch_transcripts
from store import (
    channel_dir,
    latest_extractions,
    mark_seen,
    read_concepts_json,
    seen,
    write_concepts_json,
    write_knowledge_md,
    write_video_md,
)
from weighting import rebuild

ROOT = Path(__file__).parent
WINDOW = 5

# Optional plain API key — reads public channel data with no OAuth consent screen.
_YOUTUBE_API_KEY = dotenv_values(ROOT / ".env").get("YOUTUBE_API_KEY") or os.environ.get(
    "YOUTUBE_API_KEY"
)

# Public per-channel Atom feed — no API key, no OAuth, no quota.
# Exposes the 15 most recent uploads per channel.
_ATOM = {
    "a": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}


def _load_channels() -> list[dict]:
    data = yaml.safe_load((ROOT / "channels.yaml").read_text())
    return data.get("channels", [])


def _latest_videos(yt, uploads_playlist: str, limit: int = WINDOW) -> list[dict]:
    resp = (
        yt.playlistItems()
        .list(
            part="snippet,contentDetails",
            playlistId=uploads_playlist,
            maxResults=limit,
        )
        .execute()
    )
    return [
        {
            "video_id": item["contentDetails"]["videoId"],
            "title": item["snippet"]["title"],
            "published_at": item["contentDetails"].get("videoPublishedAt")
            or item["snippet"]["publishedAt"],
        }
        for item in resp.get("items", [])
    ]


def _latest_videos_rss(channel_id: str, limit: int = WINDOW) -> list[dict]:
    """Latest uploads from the public channel Atom feed (credential-free)."""
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (yt-education-agent)"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    root = ET.fromstring(raw)
    out: list[dict] = []
    for entry in root.findall("a:entry", _ATOM)[:limit]:
        vid = entry.findtext("yt:videoId", default="", namespaces=_ATOM)
        if not vid:
            continue
        out.append(
            {
                "video_id": vid,
                "title": entry.findtext("a:title", default="", namespaces=_ATOM),
                "published_at": entry.findtext("a:published", default="", namespaces=_ATOM),
            }
        )
    return out


def process_channel(yt, channel: dict) -> int:
    handle = channel["handle"]
    title = channel["title"]
    print(f"\n=== {title} (@{handle})")
    if yt is not None:
        videos = _latest_videos(yt, channel["uploads_playlist"], WINDOW)
    else:
        videos = _latest_videos_rss(channel["id"], WINDOW)
    if not videos:
        print("  no uploads found")
        return 0
    unseen = [v for v in videos if not seen(v["video_id"])]
    transcripts: dict[str, str | None] = {}
    if unseen:
        print(f"  · fetching {len(unseen)} transcript(s)...")
        try:
            transcripts = fetch_transcripts([v["video_id"] for v in unseen])
        except Exception as exc:
            print(f"  ! transcript fetch failed: {exc}", file=sys.stderr)
    new_count = 0
    for video in videos:
        vid = video["video_id"]
        if seen(vid):
            print(f"  · seen   {vid}  {video['title'][:60]}")
            continue
        print(f"  + fetch  {vid}  {video['title'][:60]}")
        transcript = transcripts.get(vid)
        if not transcript:
            print(f"    (no transcript available — skipping)")
            continue
        try:
            extraction = extract_from_transcript(transcript[:60000], video["title"])
        except Exception as exc:
            print(f"    ! extraction failed: {exc}")
            continue
        prior_knowledge = read_concepts_json(handle)
        write_video_md(handle, vid, video["title"], video["published_at"], extraction)
        change_logged = detect_and_log(handle, vid, video["title"], extraction)
        mark_seen(
            channel["id"],
            handle,
            vid,
            video["title"],
            video["published_at"],
            extraction,
        )
        extractions = latest_extractions(channel["id"], WINDOW)
        new_knowledge = rebuild([e["extraction"] for e in extractions])
        write_concepts_json(handle, new_knowledge)
        write_knowledge_md(
            handle,
            title,
            new_knowledge,
            sources=[
                {
                    "video_id": e["video_id"],
                    "title": e["title"],
                    "published_at": e["published_at"],
                }
                for e in extractions
            ],
        )
        try:
            impact = summarize_impact(extraction, video["title"], None)
        except Exception as exc:
            impact = f"(impact summary failed: {exc})"
        try:
            body = build_email_body(
                channel_title=title,
                channel_handle=handle,
                video=video,
                extraction=extraction,
                prior_knowledge=prior_knowledge,
                new_knowledge=new_knowledge,
                change_logged=change_logged,
                impact_paragraph=impact,
            )
            evolution_tag = " ⚡ EVOLUTION" if change_logged else ""
            subject = f"[YT Education] {title}: {video['title'][:80]}{evolution_tag}"
            if send_email(subject, body):
                print(f"    ✉  email sent for {vid}")
        except Exception as exc:
            print(f"    ! email failed: {exc}", file=sys.stderr)
        new_count += 1
    if new_count == 0:
        extractions = latest_extractions(channel["id"], WINDOW)
        if extractions and not (channel_dir(handle) / "knowledge.md").exists():
            knowledge = rebuild([e["extraction"] for e in extractions])
            write_concepts_json(handle, knowledge)
            write_knowledge_md(
                handle,
                title,
                knowledge,
                sources=[
                    {
                        "video_id": e["video_id"],
                        "title": e["title"],
                        "published_at": e["published_at"],
                    }
                    for e in extractions
                ],
            )
    print(f"  → {new_count} new video(s) processed this pass")
    return new_count


def run_once() -> int:
    yt = None
    try:
        if _YOUTUBE_API_KEY:
            yt = build("youtube", "v3", developerKey=_YOUTUBE_API_KEY)
        else:
            creds = load_cached_credentials()
            if creds is None:
                raise RuntimeError(
                    "no cached OAuth token — run `python auth.py` once, "
                    "or set YOUTUBE_API_KEY in .env"
                )
            yt = build("youtube", "v3", credentials=creds)
    except Exception as exc:
        print(
            f"[info] YouTube Data API unavailable ({type(exc).__name__}: {exc})",
            file=sys.stderr,
        )
        print(
            "[info] falling back to public RSS feeds — no credentials required",
            file=sys.stderr,
        )
    total = 0
    for channel in _load_channels():
        total += process_channel(yt, channel)
    return total


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--once", action="store_true", help="run a single pass and exit"
    )
    args = parser.parse_args()
    new = run_once()
    print(f"\nDone. {new} new video(s) processed.\n")