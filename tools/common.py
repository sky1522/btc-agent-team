"""데이터 도구 공용 함수: 설정 로드, KST 시각, 파일 쓰기."""

from __future__ import annotations

import json
import os
import sys
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "tools" / "config.toml"
KST = timezone(timedelta(hours=9), "KST")


def utf8_stdout() -> None:
    """Windows 콘솔·파이프 기본 인코딩(cp949)에서 한글이 깨지지 않게 UTF-8로 고정."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    with open(path, "rb") as f:
        return tomllib.load(f)


def resolve(rel: str, root: Path = ROOT) -> Path:
    return root / rel


def now_kst() -> datetime:
    return datetime.now(KST)


def fmt_kst(dt: datetime) -> str:
    """사람이 읽는 KST 표기: 2026-10-31 14:45 KST"""
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s)


def write_json_atomic(path: Path, data: Any) -> None:
    """임시 파일에 쓴 뒤 교체. 대시보드가 반쯤 쓰인 파일을 읽지 않게 한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def append_jsonl(path: Path, record: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows
