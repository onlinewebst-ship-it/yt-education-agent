"""Transcript fetching.

Two providers, tried in order:
  1. Apify (karamelo/youtube-transcripts) — used when APIFY_TOKEN is set in .env.
  2. youtube-transcript-api — keyless fallback that talks to YouTube directly.

`fetch_transcripts` returns {video_id: transcript_text or None} and never raises
for a single-video failure; it only raises if *both* providers are unavailable.
"""

from __future__ import annotations

import html
import os
import time
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).parent
_ENV = dotenv_values(ROOT / ".env")
_APIFY_TOKEN = _ENV.get("APIFY_TOKEN") or os.environ.get("APIFY_TOKEN")
_ACTOR = "karamelo/youtube-transcripts"

# Set TRANSCRIPT_PROVIDER=apify to force Apify even when the keyless path works.
_PROVIDER = (_ENV.get("TRANSCRIPT_PROVIDER") or os.environ.get("TRANSCRIPT_PROVIDER") or "").lower()

# YouTube rate-limits bursts of caption requests (IpBlocked). Space keyless
# fetches out and retry with backoff rather than silently returning no transcript.
_DELAY = float(_ENV.get("TRANSCRIPT_DELAY_SECONDS") or 3.0)
_RETRIES = int(_ENV.get("TRANSCRIPT_RETRIES") or 3)

# Optional http(s) proxy for the keyless path — set TRANSCRIPT_PROXY when the
# host IP is throttled by YouTube (VPS/datacentre IPs are blocked more readily).
_PROXY = _ENV.get("TRANSCRIPT_PROXY") or os.environ.get("TRANSCRIPT_PROXY") or ""


def _fetch_via_apify(video_ids: list[str]) -> dict[str, str | None]:
    from apify_client import ApifyClient

    if not _APIFY_TOKEN:
        raise RuntimeError("APIFY_TOKEN not found in .env")
    client = ApifyClient(_APIFY_TOKEN)
    urls = [f"https://www.youtube.com/watch?v={vid}" for vid in video_ids]
    run = client.actor(_ACTOR).call(
        run_input={
            "urls": urls,
            "outputFormat": "singleStringText",
            "maxRetries": 8,
            "channelIDBoolean": True,
            "datePublishedBoolean": True,
        }
    )
    out: dict[str, str | None] = {vid: None for vid in video_ids}
    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        vid = item.get("videoId")
        captions = item.get("captions") or ""
        if vid and captions:
            out[vid] = html.unescape(captions).strip()
    return out


class IpBlocked(RuntimeError):
    """YouTube is throttling caption requests from this IP."""


def _is_ip_blocked(exc: BaseException) -> bool:
    return type(exc).__name__ == "IpBlocked" or "blocking requests from your IP" in str(exc)


def _make_api():
    from youtube_transcript_api import YouTubeTranscriptApi

    if not _PROXY:
        return YouTubeTranscriptApi()
    try:  # v1.x takes a proxy config object
        from youtube_transcript_api.proxies import GenericProxyConfig

        return YouTubeTranscriptApi(
            proxy_config=GenericProxyConfig(http_url=_PROXY, https_url=_PROXY)
        )
    except Exception:
        return YouTubeTranscriptApi()


def _fetch_one_keyless(video_id: str) -> str | None:
    """Fetch one transcript keyless.

    Raises IpBlocked when YouTube throttles the IP, so the caller can stop the
    batch instead of hammering a blocked endpoint.
    """
    api = _make_api()

    def _snippets_to_text(snippets) -> str:
        parts = []
        for s in snippets:
            text = s.text if hasattr(s, "text") else s.get("text", "")
            if text:
                parts.append(text)
        return " ".join(parts).replace("\n", " ").strip()

    attempts = []
    if hasattr(api, "fetch"):  # v1.x: api.fetch(video_id, languages=[...])
        attempts = [
            lambda: api.fetch(video_id, languages=["en"]),
            lambda: api.fetch(video_id, languages=["en-GB", "en-US"]),
            lambda: api.fetch(video_id),
        ]
    else:  # v0.6.x: classmethod get_transcript(video_id)
        from youtube_transcript_api import YouTubeTranscriptApi

        get = getattr(YouTubeTranscriptApi, "get_transcript", None)
        if get is not None:
            attempts = [lambda: get(video_id)]

    for attempt in attempts:
        try:
            text = _snippets_to_text(attempt())
        except Exception as exc:
            if _is_ip_blocked(exc):
                raise IpBlocked(str(exc)[:200]) from exc
            continue
        if text:
            return text
    return None


def _fetch_via_keyless(video_ids: list[str]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for i, vid in enumerate(video_ids):
        if i:
            time.sleep(_DELAY)
        text = None
        for attempt in range(_RETRIES + 1):
            if attempt:
                time.sleep(_DELAY * (2**attempt))
            try:
                text = _fetch_one_keyless(vid)
            except IpBlocked:
                print(
                    "    ! YouTube is rate-limiting transcripts from this IP — "
                    "stopping this batch; unstored videos retry next pass"
                )
                return out
            if text:
                break
        out[vid] = text
    return out


def fetch_transcripts(video_ids: list[str]) -> dict[str, str | None]:
    """Return {video_id: transcript_text or None} for each video."""
    if not video_ids:
        return {}

    order = ["apify", "keyless"]
    if _PROVIDER == "keyless" or not _APIFY_TOKEN:
        order = ["keyless"] + (["apify"] if _APIFY_TOKEN else [])

    errors: list[str] = []
    out: dict[str, str | None] = {vid: None for vid in video_ids}
    for provider in order:
        pending = [vid for vid in video_ids if not out.get(vid)]
        if not pending:
            break
        fn = _fetch_via_apify if provider == "apify" else _fetch_via_keyless
        try:
            got = fn(pending)
        except Exception as exc:  # provider entirely unusable — try the next one
            errors.append(f"{provider}: {type(exc).__name__}: {exc}")
            continue
        for vid, text in got.items():
            if text:
                out[vid] = text

    if not any(out.values()) and errors:
        raise RuntimeError("all transcript providers failed — " + "; ".join(errors))
    return out
