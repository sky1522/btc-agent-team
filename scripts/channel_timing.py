"""텔레그램 지시별 응답 시간 측정.

Claude Code 세션 기록(~/.claude/projects/<프로젝트>/<세션>.jsonl)에서
텔레그램 수신 시각과 reply 도구 호출 시각을 뽑아 지시마다
첫 회신(접수)까지, 마지막 회신(결과)까지 걸린 시간을 보여준다. 읽기만 한다.

사용: uv run python scripts/channel_timing.py            (가장 최근 세션)
      uv run python scripts/channel_timing.py <세션.jsonl>
"""

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
REPLY_TOOL = "mcp__plugin_telegram_telegram__reply"
CHANNEL_RE = re.compile(r'<channel source="plugin:telegram[^"]*"[^>]*>(.*?)</channel>', re.S)


def project_transcripts() -> Path:
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(ROOT))
    return Path.home() / ".claude" / "projects" / slug


def ts(entry: dict) -> datetime | None:
    raw = entry.get("timestamp")
    return datetime.fromisoformat(raw.replace("Z", "+00:00")) if raw else None


def texts(content) -> list[str]:
    if isinstance(content, str):
        return [content]
    out = []
    for c in content or []:
        if isinstance(c, dict):
            if isinstance(c.get("text"), str):
                out.append(c["text"])
            if isinstance(c.get("content"), str):
                out.append(c["content"])
    return out


def main() -> None:
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        files = sorted(project_transcripts().glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
        path = files[-1]
    events = []  # (time, kind, text)
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = ts(e)
        msg = e.get("message") or {}
        if e.get("type") == "user" and t:
            for txt in texts(msg.get("content")):
                for m in CHANNEL_RE.finditer(txt):
                    events.append((t, "in", m.group(1).strip()))
        if e.get("type") == "assistant" and t:
            for c in msg.get("content") or []:
                if not isinstance(c, dict) or c.get("type") != "tool_use":
                    continue
                if c.get("name") == REPLY_TOOL:
                    events.append((t, "reply", (c.get("input") or {}).get("text", "")))
    events.sort(key=lambda x: x[0])

    print(f"세션: {path.name}")
    print("| 수신(KST) | 지시 | 첫 회신까지 | 첫 회신 내용 | 마지막 회신까지 | 회신 수 |")
    print("|---|---|---|---|---|---|")
    for i, (t, kind, text) in enumerate(events):
        if kind != "in":
            continue
        replies = []
        for t2, k2, txt2 in events[i + 1:]:
            if k2 == "in":
                break
            replies.append((t2, txt2))
        if replies:
            first = (replies[0][0] - t).total_seconds()
            last = (replies[-1][0] - t).total_seconds()
            head = replies[0][1].splitlines()[0][:40] if replies[0][1] else ""
            print(f"| {t.astimezone(KST):%H:%M:%S} | {text[:30]} | {first:.0f}s | {head} | "
                  f"{last:.0f}s | {len(replies)} |")
        else:
            print(f"| {t.astimezone(KST):%H:%M:%S} | {text[:30]} | - | (회신 없음) | - | 0 |")


if __name__ == "__main__":
    main()
