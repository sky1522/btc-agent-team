"""claude -p --output-format stream-json 결과에서 에이전트 호출·도구 사용·거부·최종 답을 요약한다.

사용: uv run python scripts/show_run.py data/logs/<run>.stream.jsonl
"""

import json
import sys

sys.stdout.reconfigure(encoding="utf-8")


def main(path: str) -> None:
    final = None
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        ev = json.loads(line)
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init":
            print(f"[init] model={ev.get('model')} agents={ev.get('agents')}")
            print(f"       plugins={[p.get('name') for p in ev.get('plugins', [])]}")
        elif t == "assistant":
            parent = ev.get("parent_tool_use_id")
            who = "sub" if parent else "총괄"
            for c in ev["message"].get("content", []):
                if c.get("type") == "tool_use":
                    inp = c.get("input", {})
                    if c["name"] in ("Agent", "Task"):
                        agent, desc = inp.get("subagent_type"), inp.get("description")
                        print(f"[{who}] Agent → {agent} : {desc}")
                    else:
                        arg = inp.get("command") or inp.get("file_path") or inp.get("url") or ""
                        print(f"[{who}] {c['name']} {str(arg)[:90]}")
        elif t == "user":
            for c in ev.get("message", {}).get("content", []) or []:
                if isinstance(c, dict) and c.get("is_error"):
                    txt = c.get("content")
                    txt = txt if isinstance(txt, str) else json.dumps(txt, ensure_ascii=False)
                    print(f"   !! 오류/거부: {txt[:160]}")
        elif t == "result":
            final = ev
    if final:
        print(f"\n[result] {final.get('subtype')} turns={final.get('num_turns')} "
              f"duration={final.get('duration_ms', 0) / 1000:.0f}s "
              f"denials={len(final.get('permission_denials') or [])}")
        for d in final.get("permission_denials") or []:
            detail = json.dumps(d.get("tool_input"), ensure_ascii=False)[:120]
            print(f"   denied: {d.get('tool_name')} {detail}")
        print("\n" + (final.get("result") or ""))


if __name__ == "__main__":
    main(sys.argv[1])
