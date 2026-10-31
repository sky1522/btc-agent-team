"""하위 에이전트 호출 기록 훅.

Claude Code가 훅 이벤트마다 stdin으로 JSON을 넘겨준다. data/logs/agents.jsonl에 한 줄씩 남긴다.
- PreToolUse(Agent): 총괄이 배정한 순간  → event "assign" (agent, description)
- SubagentStart     : 하위 에이전트 실행 시작 → event "start"
- SubagentStop      : 하위 에이전트 종료     → event "stop"
기록 실패가 작업을 막으면 안 되므로 어떤 오류도 삼키고 0으로 끝낸다.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent.parent
LOG = ROOT / "data" / "logs" / "agents.jsonl"
EVENTS = {"PreToolUse": "assign", "SubagentStart": "start", "SubagentStop": "stop"}


def main() -> None:
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
        tool_input = payload.get("tool_input") or {}
        event = payload.get("hook_event_name", "")
        record = {
            "ts": datetime.now(KST).isoformat(timespec="milliseconds"),
            "event": EVENTS.get(event, event),
            "agent": tool_input.get("subagent_type") or payload.get("agent_type") or "",
            "description": tool_input.get("description", ""),
            "agent_id": payload.get("agent_id", ""),
            "tool_use_id": payload.get("tool_use_id", ""),
            "session_id": payload.get("session_id", ""),
        }
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    main()
