import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from readyproof.config import Limits, Settings  # noqa: E402
from readyproof.core import new_project  # noqa: E402
from readyproof.ingest import ingest_bytes  # noqa: E402
from readyproof.logic import rules  # noqa: E402

FILES = os.path.join(ROOT, "readyproof", "demos", "files")


def read(name):
    with open(os.path.join(FILES, name), "rb") as f:
        return f.read()


@pytest.fixture(autouse=True)
def no_paid_api(monkeypatch):
    """自動テストでは有料APIを絶対に呼ばない（呼ぼうとしたら失敗させる）。"""
    import anthropic

    def boom(*a, **k):
        raise AssertionError("自動テストで有料APIを呼び出そうとしました")

    monkeypatch.setattr(anthropic, "Anthropic", boom)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture
def limits():
    return Limits()


@pytest.fixture
def settings():
    return Settings()


@pytest.fixture
def project():
    p = new_project("テスト案件")
    p["products"].append({"id": "PR-001", "name": "テスト製品", "vendor": "架空ベンダー", "plan": "スタンダード",
                          "edition": "1.0", "delivery": "SaaS", "as_of": "", "notes": ""})
    return p


@pytest.fixture
def deck_project(project, limits):
    """デモ1の PowerPoint を読み込んだ案件。"""
    res = ingest_bytes("deck.pptx", read("demo1_keihinavi_proposal.pptx"), limits).to_dict()
    src = rules.add_source(project, res, {"file_name": "deck.pptx", "name": "提案資料", "product_id": "PR-001"})
    return project, src
