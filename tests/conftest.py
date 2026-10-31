import json
from pathlib import Path

import pytest

from common import ROOT, load_config

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def config():
    """실제 tools/config.toml을 그대로 쓴다 (설정과 테스트가 어긋나지 않게)."""
    return load_config(ROOT / "tools" / "config.toml")


@pytest.fixture
def raw_response():
    return json.loads((FIXTURES / "pools_sample.json").read_text(encoding="utf-8"))


@pytest.fixture
def multi_day_history():
    lines = (FIXTURES / "history_multi_day.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(x) for x in lines if x.strip()]
