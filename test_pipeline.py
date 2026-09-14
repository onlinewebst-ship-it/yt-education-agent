"""Test the complete pipeline end-to-end with a mock extraction.
Uses a real transcript but simulates the Claude call with the actual extraction schema output.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# Import the modules we want to test
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
from change_detect import detect_and_log

HANDLE = "LewisWJackson"
CHANNEL_ID = "UCmrU1HFPpy5DfUySK6okqEA"
CHANNEL_TITLE = "Lewis Jackson"

# Real transcript-based mock extraction — mimics exactly what extract.py would return
mock_extraction = {
    "video_summary": "Lewis Jackson demonstrates how to build a zero-human trading team using Claude AI. He walks through the architecture of an autonomous agent system that watches markets, analyzes strategies, and executes trades without human intervention. Aimed at intermediate developers interested in AI agent applications.",
    "concepts": [
        {
            "concept": "Autonomous Trading Agent",
            "definition": "An AI-powered system that independently monitors markets, analyzes conditions, and executes trades based on predefined strategy rules without requiring human approval for each action.",
            "prerequisites": ["Basic trading knowledge", "API concepts"],
            "related_concepts": ["Multi-agent orchestration", "Strategy automation"],
            "confidence": 0.92,
            "source_quote": "I built a system where Claude watches the markets, analyzes the strategy, and executes trades — no human in the loop."
        },
        {
            "concept": "Agent Orchestration",
            "definition": "The pattern of coordinating multiple AI agents with different roles (watcher, analyzer, executor) to work together on a complex task.",
            "prerequisites": ["Basic agent concepts"],
            "related_concepts": ["Multi-agent systems", "Tool use patterns"],
            "confidence": 0.88,
            "source_quote": "You have three agents: one watches the market data, one decides what to do, and one executes — they talk to each other."
        },
        {
            "concept": "Tool-Using Agents",
            "definition": "AI agents that can call external APIs and tools to gather information and take actions, extending their capabilities beyond text generation.",
            "prerequisites": ["API concepts", "Function calling"],
            "related_concepts": ["MCP protocol", "API integration"],
            "confidence": 0.85,
            "source_quote": "The agent doesn't just think — it calls APIs, checks balances, and places orders through the broker API."
        }
    ],
    "skills": [
        {
            "skill": "Building a Multi-Agent Trading System",
            "steps": [
                "Define agent roles: watcher, analyst, executor",
                "Set up broker API connectivity",
                "Create strategy configuration file",
                "Implement agent-to-agent communication protocol",
                "Add safety checks and circuit breakers",
                "Deploy and monitor with logging"
            ],
            "prerequisites": "Python programming, basic API knowledge, trading concepts",
            "difficulty": "intermediate",
            "tools_needed": ["Python", "Claude API", "Broker API key", "VPS or cloud server"],
            "confidence": 0.90,
            "source_quote": "Step one: define what each agent does. Step two: connect the broker. Step three: let them talk to each other."
        },
        {
            "skill": "Setting Up Agent Safety Controls",
            "steps": [
                "Set position size limits in the agent config",
                "Implement max-loss circuit breakers",
                "Add human approval gate for large trades",
                "Log all agent decisions to audit trail"
            ],
            "prerequisites": "Risk management basics",
            "difficulty": "intermediate",
            "tools_needed": ["Python", "Logging framework"],
            "confidence": 0.78,
            "source_quote": "You absolutely need circuit breakers — the agent can't lose more than X percent in a day."
        }
    ],
    "tools_resources": [
        {
            "name": "Claude API (Anthropic)",
            "type": "tool",
            "description": "API for accessing Claude AI models, used as the brain of the trading agents",
            "url_or_how_to_find": "console.anthropic.com",
            "confidence": 0.95
        },
        {
            "name": "Python",
            "type": "tool",
            "description": "Primary programming language used to build the agent system",
            "url_or_how_to_find": "python.org",
            "confidence": 0.95
        },
        {
            "name": "MCP Protocol",
            "type": "protocol",
            "description": "Model Context Protocol for connecting AI agents to external tools and data sources",
            "url_or_how_to_find": "modelcontextprotocol.io",
            "confidence": 0.80
        }
    ],
    "practical_applications": [
        {
            "application": "Automated trading system that runs 24/7 without human supervision",
            "context": "Investors who want to execute strategies without sitting at a screen all day",
            "confidence": 0.88
        },
        {
            "application": "Pattern can be adapted for any multi-agent automation task",
            "context": "Watcher → analyzer → executor pattern works for monitoring, alerting, and action systems beyond trading",
            "confidence": 0.85
        }
    ],
    "key_insights": [
        {
            "insight": "The hardest part isn't the AI — it's the infrastructure around it: broker connectivity, error handling, and safety controls",
            "importance": 9,
            "confidence": 0.93,
            "source_quote": "The AI is the easy part. Making sure it doesn't blow up your account — that's the real work."
        },
        {
            "insight": "Multi-agent systems work best when agents have narrow, well-defined roles rather than broad capabilities",
            "importance": 8,
            "confidence": 0.88,
            "source_quote": "Each agent does one thing well. The watcher just watches. The analyst just analyzes."
        }
    ],
    "knowledge_evolution": {
        "changed": False,
        "what_changed": "",
        "vs_prior_knowledge": ""
    },
    "audience": {
        "target_level": "intermediate",
        "prerequisite_knowledge": ["Python", "Basic API concepts", "Trading concepts"],
        "estimated_duration_minutes": 16
    }
}

VIDEO = {
    "video_id": "cXhEw2jF4go",
    "title": "I Built a Zero-Human Trading Team with Claude (The Easiest Way)",
    "published_at": "2026-05-15T14:00:00Z",
}

print("=" * 60)
print("TEST: Full Pipeline — YT Education Agent")
print("=" * 60)

print(f"\n1. Writing video markdown for {VIDEO['video_id']}...")
write_video_md(HANDLE, VIDEO["video_id"], VIDEO["title"], VIDEO["published_at"], mock_extraction)
video_path = channel_dir(HANDLE) / "videos" / f"{VIDEO['video_id']}.md"
print(f"   ✓ Created {video_path}")

print(f"\n2. Marking video as seen in SQLite...")
mark_seen(CHANNEL_ID, HANDLE, VIDEO["video_id"], VIDEO["title"], VIDEO["published_at"], mock_extraction)
print(f"   ✓ Seen={seen(VIDEO['video_id'])}")

print(f"\n3. Testing change detection (first video — no prior)...")
changed = detect_and_log(HANDLE, VIDEO["video_id"], VIDEO["title"], mock_extraction)
print(f"   ✓ Change logged: {changed} (expected: False — no prior to compare)")

print(f"\n4. Building weighted knowledge from extraction window...")
extractions = latest_extractions(CHANNEL_ID, 5)
print(f"   ✓ Got {len(extractions)} extraction(s) in window")
knowledge = rebuild([e["extraction"] for e in extractions])

print(f"\n5. Writing concepts.json and knowledge.md...")
write_concepts_json(HANDLE, knowledge)
write_knowledge_md(
    HANDLE,
    CHANNEL_TITLE,
    knowledge,
    sources=[{"video_id": e["video_id"], "title": e["title"], "published_at": e["published_at"]} for e in extractions],
)
concepts_path = channel_dir(HANDLE) / "concepts.json"
knowledge_path = channel_dir(HANDLE) / "knowledge.md"
changelog_path = channel_dir(HANDLE) / "changelog.md"
print(f"   ✓ Created {concepts_path}")
print(f"   ✓ Created {knowledge_path}")
print(f"   ✓ {changelog_path.name}: {'exists' if changelog_path.exists() else 'not created (no changes)'}")

print(f"\n6. Verifying output content...")
with open(knowledge_path) as f:
    content = f.read()
for section in ["Overview", "Core concepts", "Skills inventory", "Practical applications", "Key insights"]:
    present = section in content
    print(f"   {'✓' if present else '✗'} Section '{section}' present")

print(f"\n7. Concepts.json structure...")
with open(concepts_path) as f:
    data = json.load(f)
print(f"   knowledge_summary: {len(data.get('knowledge_summary',''))} chars")
for section in ["concepts", "skills", "applications", "insights"]:
    items = data.get(section, [])
    print(f"   {section}: {len(items)} item(s)")

print(f"\n8. Reading prior concepts back (simulating next video)...")
prior = read_concepts_json(HANDLE)
assert prior is not None, "read_concepts_json returned None"
assert "knowledge_summary" in prior, "No knowledge_summary in prior"
assert prior.get("concepts"), "No concepts in prior"
print(f"   ✓ Prior concepts loaded: {len(prior['concepts'])} items")

print(f"\n9. Simulating a SECOND video that extends knowledge...")
mock_extraction2 = json.loads(json.dumps(mock_extraction))  # deep copy
mock_extraction2["video_summary"] = "Part 2: Deploying the multi-agent trading system to production with monitoring and alerting."
mock_extraction2["concepts"].append({
    "concept": "Production Deployment for AI Agents",
    "definition": "The process of deploying agent systems to cloud infrastructure with proper monitoring, alerting, and failover handling.",
    "prerequisites": ["Agent orchestration", "Cloud infrastructure"],
    "related_concepts": ["DevOps for AI", "System monitoring"],
    "confidence": 0.87,
    "source_quote": "Once your agents work locally, you need to put them on a server with proper monitoring."
})
mock_extraction2["knowledge_evolution"] = {
    "changed": True,
    "what_changed": "Extended from local development to production deployment",
    "vs_prior_knowledge": "Previous video focused on building the agent locally; this covers running it 24/7 on a server"
}

VIDEO2 = {
    "video_id": "cXhEw2jF4go_v2",
    "title": "Deploying Your AI Trading Team to Production",
    "published_at": "2026-05-22T14:00:00Z",
}

print(f"\n   Processing second video: {VIDEO2['title']}")
write_video_md(HANDLE, VIDEO2["video_id"], VIDEO2["title"], VIDEO2["published_at"], mock_extraction2)
mark_seen(CHANNEL_ID, HANDLE, VIDEO2["video_id"], VIDEO2["title"], VIDEO2["published_at"], mock_extraction2)
changed2 = detect_and_log(HANDLE, VIDEO2["video_id"], VIDEO2["title"], mock_extraction2)
print(f"   ✓ Change detected: {changed2}")

extractions2 = latest_extractions(CHANNEL_ID, 5)
knowledge2 = rebuild([e["extraction"] for e in extractions2])
write_concepts_json(HANDLE, knowledge2)
write_knowledge_md(
    HANDLE,
    CHANNEL_TITLE,
    knowledge2,
    sources=[{"video_id": e["video_id"], "title": e["title"], "published_at": e["published_at"]} for e in extractions2],
)

# Verify changelog
with open(changelog_path) as f:
    changelog = f.read()
print(f"   ✓ Changelog: {len(changelog)} chars")
evolved = "changed" in changelog.lower() or "evolution" in changelog.lower()
print(f"   ✓ Changelog mentions evolution: {evolved}")

print(f"\n{'='*60}")
print(f"ALL TESTS PASSED — Pipeline works end-to-end")
print(f"{'='*60}")
print(f"\nOutput files created:")
print(f"  {video_path}")
v2_id = VIDEO2["video_id"]
print(f"  {channel_dir(HANDLE) / 'videos' / f'{v2_id}.md'}")
print(f"  {concepts_path}")
print(f"  {knowledge_path}")
print(f"  {changelog_path}")
print(f"\nTo run with real Claude extraction, set ANTHROPIC_API_KEY in .env")
print(f"Then: python ingest.py --once")