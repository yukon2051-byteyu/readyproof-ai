"""案件データの基本構造・ID・状態区分。

案件は1つの dict（JSON にそのまま保存できる形）で扱う。
画面・AI・出力はすべてこの dict を読み書きする。
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone, timedelta

from .config import SCHEMA_VERSION, APP_NAME_EN

JST = timezone(timedelta(hours=9))


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def fingerprint(obj) -> str:
    """内容の指紋（短いハッシュ）。版や根拠の変更検出に使う。"""
    data = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:12]


# ---- 区分（画面の言葉）。値そのものを JSON に保存する ----
SOURCE_KINDS = ["製品説明", "機能一覧", "マニュアル", "ベンダー提案書", "質問と回答", "その他"]
SOURCE_STATUS = ["有効", "旧版", "参考"]
OWNER_KINDS = ["製品", "自社"]  # 資料が製品側か自社手順書か

REQ_PRIORITY = ["必須", "望ましい", "任意"]
REQ_STATUS = ["下書き", "確定", "廃止"]

DIAG_CATEGORIES = [
    "そのまま対応できる見込み",
    "標準設定で対応できる見込み",
    "追加対応の検討が必要",
    "対応不可との記載・確認済み発言あり",
    "情報不足・ベンダー確認が必要",
    "根拠間に矛盾あり",
]
DIAG_SHORT = {
    "そのまま対応できる見込み": "標準で対応見込み",
    "標準設定で対応できる見込み": "設定で対応見込み",
    "追加対応の検討が必要": "追加対応を検討",
    "対応不可との記載・確認済み発言あり": "対応不可の根拠あり",
    "情報不足・ベンダー確認が必要": "情報不足・要確認",
    "根拠間に矛盾あり": "根拠に矛盾",
}
REVIEW_STATUS = ["未確認", "要修正", "人が確認済み"]
ORIGINS = ["AI生成", "準備済みのデモ結果", "手動"]

EVIDENCE_KINDS = ["資料の記載", "営業・ベンダーの説明", "ベンダー回答", "自社資料", "実機テスト"]

SPEAKER_ROLES = ["未分類", "営業担当者", "ベンダー技術者", "自社担当者", "その他", "不明"]
VENDOR_ROLES = {"営業担当者", "ベンダー技術者"}
UTTERANCE_TYPES = [
    "未分類", "質問", "要望", "回答（可能）", "回答（不可）", "回答（条件付き）",
    "確約", "将来予定", "未回答・調査中", "推測・未確定", "その他",
]
UTTERANCE_FLAGS = ["聞き取り不能あり", "重複発話", "数値・金額を要確認", "否定表現を要確認", "製品名を要確認"]
CONTENT_REVIEW = ["未確認", "確認済み"]

QUESTION_STATUS = ["下書き", "確定", "送付済み", "回答あり", "回答確認済み", "取り下げ"]
ANSWER_SOURCES = ["手動入力", "資料", "確認済み営業発言"]

ACTION_TYPES = [
    "不具合修正", "標準設定の変更", "手順・教育の改善", "社内ルールの確認・見直し",
    "機能追加・カスタマイズ", "外部連携・別手段", "調査依頼", "別製品の検討", "対応不要・見送り",
]
ACTION_STATUS = ["候補", "採用", "不採用"]

REQUEST_KINDS = ["設定変更依頼", "改修依頼", "不具合修正依頼", "調査依頼", "その他"]
REQUEST_STATUS = ["下書き", "確定", "送付済み", "回答待ち", "対応検討中", "対応中", "テスト待ち", "完了", "見送り"]
REQUEST_PHASE = ["資料診断段階の懸念", "テストで発生した現象"]

TEST_VIEWPOINTS = ["通常操作", "例外・エラー", "境界値", "権限", "承認・差し戻し", "設定・改修箇所", "既存動作の再確認"]
TEST_IMPORTANCE = ["高", "中", "低"]
TEST_STATUS = ["下書き", "確定", "廃止"]

RUN_STATUS = ["未実施", "実施中", "完了", "実施不能"]
RUN_RESULT = ["未判定", "合格", "不合格"]

DECISIONS = ["未判断", "導入可", "条件付き導入可", "導入延期"]


def new_project(name: str = "新しい案件", demo_id: str | None = None) -> dict:
    ts = now_iso()
    return {
        "schema_version": SCHEMA_VERSION,
        "app": APP_NAME_EN,
        "project": {
            "id": "PJ-001",
            "name": name,
            "target_business": "",
            "purpose": "",
            "department": "",
            "constraints": "",
            "demo_id": demo_id,
            "created_at": ts,
            "updated_at": ts,
        },
        "products": [],
        "sources": [],
        "recordings": [],
        "requirements": [],
        "diagnoses": [],
        "questions": [],
        "actions": [],
        "requests": [],
        "tests": [],
        "runs": [],
        "decision": {
            "value": "未判断", "by": "", "date": "", "reason": "", "conditions": "",
            "snapshot": None, "history": [],
        },
        "audit_log": [],
        "id_counters": {},
    }


PREFIX = {
    "products": "PR", "sources": "DOC", "recordings": "REC", "requirements": "REQ",
    "diagnoses": "DG", "questions": "Q", "actions": "ACT", "requests": "CR",
    "tests": "T", "runs": "RUN",
}


def next_id(project: dict, collection: str) -> str:
    counters = project.setdefault("id_counters", {})
    existing = {x.get("id") for x in project.get(collection, [])}
    n = counters.get(collection, 0)
    while True:
        n += 1
        cand = f"{PREFIX[collection]}-{n:03d}"
        if cand not in existing:
            counters[collection] = n
            return cand


def find(project: dict, collection: str, item_id: str) -> dict | None:
    for x in project.get(collection, []):
        if x.get("id") == item_id:
            return x
    return None


def log(project: dict, action: str, target: str, by: str = "", detail: str = "") -> None:
    """操作履歴。本文は入れず、何をしたかだけ残す。"""
    project.setdefault("audit_log", []).append(
        {"at": now_iso(), "action": action, "target": target, "by": by, "detail": detail[:200]}
    )
    project["project"]["updated_at"] = now_iso()


def snapshot(obj: dict, exclude: tuple = ("history",)) -> dict:
    return {k: copy.deepcopy(v) for k, v in obj.items() if k not in exclude}


def bump_version(obj: dict, by: str = "", reason: str = "") -> None:
    """確定済みの内容を変更するとき、旧版を履歴に残して版を上げる。"""
    hist = obj.setdefault("history", [])
    hist.append({"version": obj.get("version", 1), "at": now_iso(), "by": by, "reason": reason,
                 "data": snapshot(obj)})
    obj["version"] = int(obj.get("version", 1)) + 1


def primary_product(project: dict) -> dict | None:
    return project["products"][0] if project.get("products") else None
