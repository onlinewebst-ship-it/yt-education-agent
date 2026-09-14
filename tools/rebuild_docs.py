"""Rebuild a channel's living documents from stored extractions.

No model calls and no network — it re-renders knowledge.md and concepts.json
straight from state.db. Useful after changing the weighting/rendering logic.

    python tools/rebuild_docs.py            # every channel in channels.yaml
    python tools/rebuild_docs.py LewisWJackson 3b1b
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from store import latest_extractions, write_concepts_json, write_knowledge_md  # noqa: E402
from weighting import rebuild  # noqa: E402


def main(handles: list[str]) -> int:
    channels = yaml.safe_load((ROOT / "channels.yaml").read_text()).get("channels", [])
    targets = [c for c in channels if not handles or c["handle"] in handles]
    if not targets:
        print(f"no channel in channels.yaml matches {handles}")
        return 1
    for ch in targets:
        extractions = latest_extractions(ch["id"], 5)
        if not extractions:
            print(f"{ch['handle']}: no stored extractions — nothing to rebuild")
            continue
        knowledge = rebuild([e["extraction"] for e in extractions])
        write_concepts_json(ch["handle"], knowledge)
        write_knowledge_md(
            ch["handle"],
            ch["title"],
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
        print(f"{ch['handle']}: rebuilt from {len(extractions)} stored video(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
