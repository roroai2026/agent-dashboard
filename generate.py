#!/usr/bin/env python3
"""
Agent Dashboard Generator
Reads OpenClaw session files and produces dashboard-data.json
"""
import json
import os
import glob
import re
from datetime import datetime, timezone

STATE_DIR = os.path.expanduser("~/.openclaw/agents")
OUTPUT = os.path.join(os.path.dirname(__file__), "dashboard-data.json")

AGENT_META = {
    "main": {
        "name": "Ram",
        "emoji": "🐏",
        "role": "Personal assistant",
        "workspace": os.path.expanduser("~/.openclaw/workspace"),
    },
    "patty": {
        "name": "Patty",
        "emoji": "📊",
        "role": "AI news & stocks researcher",
        "workspace": os.path.expanduser("~/.openclaw/workspace-patty"),
    },
    "bingo": {
        "name": "Bingo",
        "emoji": "🤖",
        "role": "Developer / background worker",
        "workspace": None,
    },
}

def parse_sessions(agent_id):
    sessions_dir = os.path.join(STATE_DIR, agent_id, "sessions")
    if not os.path.isdir(sessions_dir):
        return []

    results = []
    for path in glob.glob(os.path.join(sessions_dir, "*.jsonl")):
        if ".trajectory" in path:
            continue
        session = {
            "id": os.path.basename(path).replace(".jsonl", ""),
            "created": None,
            "lastActive": None,
            "messages": 0,
            "tokensIn": 0,
            "tokensOut": 0,
            "cost": 0.0,
            "topics": [],
        }
        try:
            with open(path) as f:
                lines = [l.strip() for l in f if l.strip()]
            for line in lines:
                obj = json.loads(line)
                t = obj.get("type")

                if t == "session":
                    ts = obj.get("timestamp")
                    if ts:
                        session["created"] = ts

                elif t == "message":
                    msg = obj.get("message", {})
                    role = msg.get("role")
                    ts = msg.get("timestamp") or obj.get("timestamp")

                    if ts and (session["lastActive"] is None or ts > session["lastActive"]):
                        session["lastActive"] = ts

                    if role == "assistant":
                        usage = msg.get("usage", {}) or {}
                        session["tokensIn"] += (
                            usage.get("input", 0) or
                            usage.get("input_tokens", 0) or
                            usage.get("inputTokens", 0) or 0
                        )
                        session["tokensOut"] += (
                            usage.get("output", 0) or
                            usage.get("output_tokens", 0) or
                            usage.get("outputTokens", 0) or 0
                        )
                        raw_cost = usage.get("cost", 0) or usage.get("estimatedCostUsd", 0) or 0
                        if isinstance(raw_cost, dict):
                            cost = raw_cost.get("total", 0) or 0
                        else:
                            cost = raw_cost
                        session["cost"] += float(cost)

                    if role == "user":
                        session["messages"] += 1
                        content = msg.get("content", "")
                        if isinstance(content, list):
                            for c in content:
                                if isinstance(c, dict) and c.get("type") == "text":
                                    content = c.get("text", "")
                                    break
                        if isinstance(content, str):
                            # Extract clean short snippet (skip metadata blocks)
                            clean = re.sub(r'```[\s\S]*?```', '', content).strip()
                            clean = re.sub(r'\n+', ' ', clean).strip()
                            if clean and not clean.startswith('{') and len(clean) > 5:
                                snippet = clean[:80]
                                if snippet not in session["topics"]:
                                    session["topics"].append(snippet)

        except Exception as e:
            pass

        results.append(session)
    return results


def summarize_agent(agent_id):
    meta = AGENT_META.get(agent_id, {
        "name": agent_id.capitalize(),
        "emoji": "🤖",
        "role": "Agent",
        "workspace": None,
    })

    sessions = parse_sessions(agent_id)
    total_messages = sum(s["messages"] for s in sessions)
    total_tokens_in = sum(s["tokensIn"] for s in sessions)
    total_tokens_out = sum(s["tokensOut"] for s in sessions)
    total_cost = sum(s["cost"] for s in sessions)

    all_topics = []
    for s in sessions:
        all_topics.extend(s["topics"])
    recent_topics = all_topics[-5:][::-1]

    # Created = earliest session
    created_dates = [s["created"] for s in sessions if s["created"]]
    created = min(created_dates) if created_dates else None

    # Last active = most recent across sessions
    last_dates = [s["lastActive"] for s in sessions if s["lastActive"]]
    last_active = max(last_dates) if last_dates else None

    # Agent dir created time as fallback for "created"
    agent_dir = os.path.join(STATE_DIR, agent_id)
    if not created and os.path.isdir(agent_dir):
        stat = os.stat(agent_dir)
        created = datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat()

    has_sessions = os.path.isdir(os.path.join(STATE_DIR, agent_id, "sessions"))

    return {
        "id": agent_id,
        "name": meta["name"],
        "emoji": meta["emoji"],
        "role": meta["role"],
        "status": "active" if last_active else ("configured" if has_sessions else "pending"),
        "created": created,
        "lastActive": last_active,
        "totalSessions": len(sessions),
        "totalMessages": total_messages,
        "totalTokensIn": total_tokens_in,
        "totalTokensOut": total_tokens_out,
        "estimatedCostUsd": round(total_cost, 4),
        "recentTopics": recent_topics,
    }


def main():
    agents = []
    agent_dirs = sorted(os.listdir(STATE_DIR)) if os.path.isdir(STATE_DIR) else []

    # Always include configured agents even if no dir yet
    included = set(agent_dirs) | set(AGENT_META.keys())
    for agent_id in sorted(included):
        agents.append(summarize_agent(agent_id))

    data = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "agents": agents,
    }

    with open(OUTPUT, "w") as f:
        json.dump(data, f, indent=2)

    print(f"✅ Generated {OUTPUT} with {len(agents)} agents")
    for a in agents:
        print(f"  {a['emoji']} {a['name']}: {a['totalSessions']} sessions, {a['totalMessages']} messages, ${a['estimatedCostUsd']:.4f}")


if __name__ == "__main__":
    main()
