"""案件の JSON 保存・読込。

- 形式の版（schema_version）を持つ
- 読込は「検証してから差し替える」。失敗しても現在の作業は変更しない
- 動画・音声・資料のバイナリは含めない（抽出本文・参照位置・話者・履歴などの関係のみ）
"""
from __future__ import annotations

import copy
import json

from ..config import SCHEMA_VERSION

MAX_JSON_MB = 30
REQUIRED_KEYS = {"schema_version", "project", "products", "sources", "recordings", "requirements", "diagnoses",
                 "questions", "actions", "requests", "tests", "runs", "decision"}
LIST_KEYS = REQUIRED_KEYS - {"schema_version", "project", "decision"}


class LoadError(Exception):
    pass


def to_json_bytes(project: dict, include_unselected_notes: bool = False,
                  include_unselected_utterances: bool = True) -> bytes:
    data = copy.deepcopy(project)
    for src in data.get("sources", []):
        for seg in src.get("segments", []):
            if seg.get("is_note") and not seg.get("selected") and not include_unselected_notes:
                seg["text"] = ""
                seg["text_omitted"] = True  # 未選択ノートの本文は保存しない
    if not include_unselected_utterances:
        for rec in data.get("recordings", []):
            for u in rec.get("utterances", []):
                if not u.get("selected", True):
                    u["raw_text"], u["edited_text"], u["history"] = "", "", []
                    u["text_omitted"] = True
    for rec in data.get("recordings", []):
        rec["media_retained"] = False  # JSON に動画本体は入らない
    return json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8")


def content_summary(project: dict) -> list[dict]:
    """保存前に、JSON に何が入るかを利用者に示す。"""
    notes_unsel = sum(1 for s in project["sources"] for g in s["segments"] if g.get("is_note") and not g.get("selected"))
    utt = sum(len(r.get("utterances", [])) for r in project["recordings"])
    return [
        {"内容": "案件・製品情報", "件数": 1 + len(project["products"]), "備考": ""},
        {"内容": "資料（抽出本文・参照位置・警告）", "件数": len(project["sources"]), "備考": "元ファイル本体は含みません"},
        {"内容": "未選択の発表者ノート", "件数": notes_unsel, "備考": "初期設定では本文を保存しません"},
        {"内容": "録画の発言区間（原文・修正・話者・履歴）", "件数": utt, "備考": "動画・音声本体は含みません"},
        {"内容": "自社要件（版・履歴）", "件数": len(project["requirements"]), "備考": ""},
        {"内容": "診断と根拠", "件数": len(project["diagnoses"]), "備考": ""},
        {"内容": "質問・回答", "件数": len(project["questions"]), "備考": ""},
        {"内容": "対応方法・依頼書", "件数": len(project["actions"]) + len(project["requests"]), "備考": ""},
        {"内容": "テスト・実施結果", "件数": len(project["tests"]) + len(project["runs"]), "備考": ""},
        {"内容": "導入判断・操作履歴", "件数": 1 + len(project.get("audit_log", [])), "備考": "名前は自己申告"},
    ]


def _migrate(data: dict) -> dict:
    """将来の形式変更に備えた移行処理（現状 1.0 のみ）。"""
    ver = str(data.get("schema_version", ""))
    if ver != SCHEMA_VERSION:
        raise LoadError(f"未対応の保存形式です（形式の版 {ver or '不明'}、対応 {SCHEMA_VERSION}）。")
    data.setdefault("audit_log", [])
    data.setdefault("id_counters", {})
    return data


def from_json_bytes(raw: bytes) -> dict:
    if len(raw) > MAX_JSON_MB * 1024 * 1024:
        raise LoadError(f"ファイルが大きすぎます（上限 {MAX_JSON_MB}MB）。")
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise LoadError("JSON として読み込めませんでした（ReadyProof AI で保存したファイルか確認してください）。") from e
    if not isinstance(data, dict):
        raise LoadError("案件データの形式ではありません。")
    missing = REQUIRED_KEYS - set(data.keys())
    if missing:
        raise LoadError("案件データに必要な項目がありません：" + "、".join(sorted(missing)))
    for k in LIST_KEYS:
        if not isinstance(data[k], list):
            raise LoadError(f"項目「{k}」の形式が正しくありません。")
    if not isinstance(data["project"], dict) or not isinstance(data["decision"], dict):
        raise LoadError("案件情報または導入判断の形式が正しくありません。")
    data = _migrate(data)
    _check_relations(data)
    return data


def _check_relations(data: dict) -> None:
    """関連付けの整合性（存在しない要件を指す診断など）を確認する。"""
    req_ids = {r.get("id") for r in data["requirements"]}
    test_ids = {t.get("id") for t in data["tests"]}
    for d in data["diagnoses"]:
        if d.get("req_id") not in req_ids:
            raise LoadError(f"診断 {d.get('id')} が存在しない要件 {d.get('req_id')} を参照しています。")
    for r in data["runs"]:
        if r.get("test_id") not in test_ids:
            raise LoadError(f"実施結果 {r.get('id')} が存在しないテスト {r.get('test_id')} を参照しています。")
