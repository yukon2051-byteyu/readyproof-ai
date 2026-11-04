"""録画・発言区間の管理（原文を上書きせず、人の修正と履歴を分けて持つ）。"""
from __future__ import annotations

import re

from ..core import fingerprint, now_iso
from .evidence import (FUTURE_WORDS, NEGATIVE_WORDS, PENDING_WORDS, PLAN_WORDS, UNCERTAIN_WORDS)

_NUM = re.compile(r"[0-9０-９]|円|万|千|億|%|％|日|時間|分")


def suggest_type(text: str) -> str:
    """発言の種類の候補（キーワードによる提案。確定は人）。"""
    t = text.strip()
    if any(w in t for w in PENDING_WORDS):
        return "未回答・調査中"
    if any(w in t for w in FUTURE_WORDS):
        return "将来予定"
    if any(w in t for w in UNCERTAIN_WORDS):
        return "推測・未確定"
    if t.endswith(("か？", "か?", "ますか", "でしょうか", "ですか")) or t.endswith("？") or t.endswith("?"):
        return "質問"
    if any(w in t for w in NEGATIVE_WORDS):
        return "回答（不可）"
    if any(w in t for w in PLAN_WORDS) or "場合" in t or "条件" in t:
        return "回答（条件付き）"
    return "未分類"


def auto_flags(text: str) -> list[str]:
    flags = []
    if _NUM.search(text):
        flags.append("数値・金額を要確認")
    if any(w in text for w in NEGATIVE_WORDS) or re.search(r"(ない|ません)", text):
        flags.append("否定表現を要確認")
    return flags


def build_utterances(cues: list[dict], selected_default: bool = True) -> list[dict]:
    """文字起こし結果（または字幕）を発言区間に変換する。時刻・話者がなければ None のまま。"""
    out = []
    for i, c in enumerate(cues, start=1):
        text = c.get("text", "").strip()
        out.append({
            "id": f"U{i:03d}",
            "start": c.get("start"),
            "end": c.get("end"),
            "speaker_label": c.get("speaker_label"),  # 自動の話者ラベル（例：話者A）。誰かは人が決める
            "speaker_name": "",
            "speaker_role": "未分類",
            "speaker_confirmed": False,
            "raw_text": text,  # 自動文字起こし原文（上書き禁止）
            "edited_text": "",  # 人が修正した文章
            "history": [],
            "review_status": "未確認",
            "utterance_type": "未分類",
            "type_suggestion": suggest_type(text),
            "flags": sorted(set((c.get("flags") or []) + auto_flags(text))),
            "conditions": "",
            "selected": selected_default,
            "confidence": c.get("confidence"),
        })
    return out


def edit_utterance_text(u: dict, new_text: str, by: str = "") -> bool:
    """人による修正。原文は残し、修正履歴を追加する。"""
    current = u.get("edited_text") or u.get("raw_text", "")
    if new_text.strip() == current.strip():
        return False
    u.setdefault("history", []).append({"at": now_iso(), "by": by, "field": "文章", "from": current, "to": new_text})
    u["edited_text"] = new_text
    u["review_status"] = "未確認"  # 文章を変えたら内容確認をやり直す
    return True


def set_speaker(u: dict, role: str, name: str = "", confirmed: bool = False, by: str = "") -> None:
    before = (u.get("speaker_role"), u.get("speaker_name"), u.get("speaker_confirmed"))
    after = (role, name, confirmed)
    if before != after:
        u.setdefault("history", []).append({"at": now_iso(), "by": by, "field": "話者",
                                            "from": f"{before[0]} {before[1]} 確認={before[2]}",
                                            "to": f"{role} {name} 確認={confirmed}"})
    u["speaker_role"], u["speaker_name"], u["speaker_confirmed"] = role, name, confirmed


def apply_speaker_map(rec: dict, label: str, role: str, name: str, confirmed: bool, by: str = "") -> int:
    """同じ自動ラベル（例：話者A）の発言にまとめて話者を設定する。"""
    n = 0
    for u in rec.get("utterances", []):
        if (u.get("speaker_label") or "") == (label or ""):
            set_speaker(u, role, name, confirmed, by)
            n += 1
    return n


def media_hash(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def find_reusable_transcript(project: dict, file_hash: str, start: float, end: float | None):
    """同じ録画・同じ範囲の文字起こしがあれば再利用する（無駄な再処理の防止）。"""
    for r in project.get("recordings", []):
        if r.get("file_sha256") == file_hash and r.get("utterances"):
            rng = r.get("range") or {}
            if rng.get("start") == start and rng.get("end") == end:
                return r
    return None


def recording_fp(rec: dict) -> str:
    return fingerprint([(u["id"], u.get("edited_text") or u.get("raw_text"), u.get("speaker_role"),
                         u.get("speaker_confirmed"), u.get("review_status")) for u in rec.get("utterances", [])])
