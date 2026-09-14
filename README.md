# YT Education Agent

A 24/7 system that watches educational YouTube channels and turns the latest videos into a **living knowledge document** — automatically updated as new videos drop.

Forked from [yt-strategy-agent](https://github.com/jackson-video-resources/yt-strategy-agent). The architecture is the same modular pipeline; the extraction schema is adapted from trading strategies to **concepts, skills, tools, and insights**.

## How it works

Every 10 minutes:

```
for each channel in channels.yaml:
  fetch latest 5 video IDs
  for any new video:
    pull transcript
    Claude extracts concepts / skills / tools / insights
    detect knowledge evolution vs prior state → changelog
    re-merge rolling window with recency weighting
    group similar concepts via embedding similarity
```

For every channel you watch, you get:

- **knowledge.md** — the accumulated knowledge base as a plain-English document
- **concepts.json** — structured concept map with confidence scores, prerequisites, and related concepts
- **changelog.md** — append-only log of when understanding evolves (contradictions, refinements, skill progressions)
- **videos/*.md** — per-video extraction notes with full detail

Plus an **email alert** to your inbox whenever:
- a new video drops
- the knowledge base detects an evolution (new concept contradicting prior, skill progression)
- a genuinely new insight emerges

Newer videos are weighted more heavily, similar concepts are grouped automatically, and knowledge shifts get flagged the moment they happen.

## What it extracts

For each video, Claude extracts a structured JSON with:

| Field | What it captures |
|-------|-----------------|
| `video_summary` | 2-4 sentence overview of what the video teaches |
| `concepts` | Concepts taught, definitions, prerequisites, related concepts |
| `skills` | Step-by-step skills/techniques, difficulty level, tools needed |
| `tools_resources` | Tools, libraries, papers, or references mentioned |
| `practical_applications` | Real-world use cases |
| `key_insights` | Non-obvious takeaways and mental models |
| `knowledge_evolution` | Whether this video contradicts or extends prior knowledge |
| `audience` | Target level, prerequisite knowledge, estimated duration |

## What it costs

- **VPS:** ~£6/month (Hostinger KVM 2 recommended)
- **Anthropic API:** ~£0.10–£0.50/month for typical use
- **YouTube Data API:** free
- **Apify** (transcript fetcher): a few pence/month
- **Email alerts:** free — sent from your own Gmail

## Repo layout

```
auth.py              OAuth flow
watcher.py           Main 10-min poll loop
ingest.py            Pull transcript + extract + merge
extract.py           Claude prompt + JSON schema (education domain)
weighting.py         Recency weighting + similarity grouping
change_detect.py     Knowledge-evolution detection
store.py             SQLite + markdown IO
notify.py            Email sender (Gmail SMTP)
transcript.py        Apify transcript fetcher
channels.yaml        Channels to watch (you edit this)
scripts/
  bootstrap_vps.sh   One-shot SSH + install onto Hostinger
  watcher.service    systemd unit
tools/
  resolve_channel.py Handle/URL → channel ID
channels/<handle>/   Generated docs live here
```

## License

MIT.