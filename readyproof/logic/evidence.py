"""根拠（エビデンス）の参照・表示・検証。

根拠の形（dict）:
  資料: {"ref_type": "source", "source_id", "version", "seg_id", "quote", "kind"}
  発言: {"ref_type": "utterance", "rec_id", "rec_version", "utt_id", "quote", "kind", "context_utt_ids": []}
  回答: {"ref_type": "answer", "question_id", "quote", "kind": "ベンダー回答"}

検証で分かるのは「引用がその箇所に実在し、使ってよい箇所か」まで。
引用が要件を満たす意味かどうか（妥当性）は人が確認する。
"""
from __future__ import annotations

import re
import unicodedata

from ..core import VENDOR_ROLES, fingerprint
from ..media.subtitles import fmt_ts

VALIDITY_NOTE = "引用の実在は確認済みですが、要件を満たす意味かどうかは人が確認してください。"

PLAN_WORDS = ["上位プラン", "プレミアム", "エンタープライズ", "Enterprise", "Pro", "プロプラン", "オプション",
              "有償", "別途", "追加費用", "アドオン", "個別開発", "カスタマイズ"]
FUTURE_WORDS = ["予定", "ロードマップ", "今後", "将来", "次期", "検討中", "来期"]
UNCERTAIN_WORDS = ["おそらく", "たぶん", "多分", "と思います", "はず", "かもしれ"]
PENDING_WORDS = ["確認して回答", "確認します", "調べます", "持ち帰", "追って", "後日回答", "確認のうえ"]
NEGATIVE_WORDS = ["できません", "不可", "対応していません", "非対応", "サポートしていません", "ありません"]


def norm(text: str) -> str:
    """比較用の正規化（全角半角・空白・改行の違いを吸収）。"""
    t = unicodedata.normalize("NFKC", text or "")
    t = re.sub(r"\s+", "", t)
    return t.replace("「", "").replace("」", "").replace("『", "").replace("』", "")


def get_source(project: dict, source_id: str, version=None) -> dict | None:
    cands = [s for s in project.get("sources", []) if s["id"] == source_id]
    if version is not None:
        cands = [s for s in cands if int(s.get("version", 1)) == int(version)]
    return max(cands, key=lambda s: int(s.get("version", 1))) if cands else None


def get_segment(source: dict, seg_id: str) -> dict | None:
    return next((g for g in source.get("segments", []) if g["seg_id"] == seg_id), None)


def get_recording(project: dict, rec_id: str, version=None) -> dict | None:
    cands = [r for r in project.get("recordings", []) if r["id"] == rec_id]
    if version is not None:
        cands = [r for r in cands if int(r.get("version", 1)) == int(version)]
    return max(cands, key=lambda r: int(r.get("version", 1))) if cands else None


def get_utterance(rec: dict, utt_id: str) -> dict | None:
    return next((u for u in rec.get("utterances", []) if u["id"] == utt_id), None)


def utt_text(u: dict) -> str:
    """人が修正した文章があればそれを、なければ自動文字起こし原文を使う。"""
    return u.get("edited_text") or u.get("raw_text") or ""


def utt_confirmed(u: dict) -> bool:
    return bool(u.get("speaker_confirmed")) and u.get("review_status") == "確認済み"


def resolve(project: dict, ev: dict) -> dict:
    """根拠が指す実体（資料・箇所 / 録画・発言）を返す。見つからなければ空。"""
    if ev.get("ref_type") == "source":
        src = get_source(project, ev.get("source_id"), ev.get("version"))
        seg = get_segment(src, ev.get("seg_id")) if src else None
        return {"source": src, "segment": seg}
    if ev.get("ref_type") == "utterance":
        rec = get_recording(project, ev.get("rec_id"), ev.get("rec_version"))
        utt = get_utterance(rec, ev.get("utt_id")) if rec else None
        return {"recording": rec, "utterance": utt}
    if ev.get("ref_type") == "answer":
        q = next((x for x in project.get("questions", []) if x["id"] == ev.get("question_id")), None)
        return {"question": q}
    return {}


def evidence_label(project: dict, ev: dict, with_quote: bool = True) -> str:
    """画面・Excel 共通の根拠表示。"""
    r = resolve(project, ev)
    quote = ev.get("quote", "")
    q = f"：『{quote}』" if with_quote and quote else ""
    if ev.get("ref_type") == "source":
        src, seg = r.get("source"), r.get("segment")
        if not src or not seg:
            return f"【参照先なし】{ev.get('source_id')} {ev.get('seg_id')}{q}"
        return f"{src['name']}（{src['id']} 第{src.get('version', 1)}版）／{seg['loc_label']}{q}"
    if ev.get("ref_type") == "utterance":
        rec, u = r.get("recording"), r.get("utterance")
        if not rec or not u:
            return f"【参照先なし】{ev.get('rec_id')} {ev.get('utt_id')}{q}"
        who = u.get("speaker_role") or "未分類"
        if u.get("speaker_name"):
            who = f"{u['speaker_name']}（{who}）"
        state = "利用者確認済み" if utt_confirmed(u) else "未確認の文字起こし"
        held = f"{rec.get('held_on')}開催／" if rec.get("held_on") else ""
        return (f"{rec.get('meeting_name') or rec.get('file_name')}（録画内の発言）／{held}"
                f"{fmt_ts(u.get('start'))}～{fmt_ts(u.get('end'))}／{who}・{state}{q}")
    if ev.get("ref_type") == "answer":
        qq = r.get("question")
        if not qq:
            return f"【参照先なし】{ev.get('question_id')}{q}"
        return f"ベンダー回答（{qq['id']}・{qq.get('answer_source') or '回答元未記入'}・{qq.get('answer_date') or '日付未記入'}）{q}"
    return f"【不明な根拠】{q}"


def detect_conditions(text: str) -> list[str]:
    """プラン・オプション・将来予定・推測・未回答・否定の表現を検出する（判断は人）。"""
    found = []
    if any(w in text for w in PLAN_WORDS):
        found.append("プラン・オプション条件あり")
    if any(w in text for w in FUTURE_WORDS):
        found.append("将来予定の可能性")
    if any(w in text for w in UNCERTAIN_WORDS):
        found.append("推測・未確定の表現")
    if any(w in text for w in PENDING_WORDS):
        found.append("未回答（調査中）の表現")
    if any(w in text for w in NEGATIVE_WORDS):
        found.append("否定表現あり")
    return found


def validate_evidence(project: dict, ev: dict, product_id: str | None = None) -> dict:
    """根拠1件を検証。errors は使用不可、warnings は人の確認が必要な注意。"""
    errors, warnings = [], []
    quote = ev.get("quote", "")
    r = resolve(project, ev)
    if ev.get("ref_type") == "source":
        src, seg = r.get("source"), r.get("segment")
        if not src:
            errors.append(f"資料 {ev.get('source_id')}（第{ev.get('version')}版）が存在しません。")
        elif not seg:
            errors.append(f"箇所 {ev.get('seg_id')} が資料内に存在しません。")
        else:
            if not quote.strip():
                errors.append("引用が空です。")
            elif norm(quote) not in norm(seg["text"]):
                errors.append("引用が指定箇所の本文に見つかりません（言い換え・創作の可能性）。")
            if not seg.get("selected", True):
                errors.append("分析対象外（未選択）の箇所です。")
            if seg.get("is_note") and not seg.get("note_reviewed"):
                errors.append("内容未確認の発表者ノートです。")
            if src.get("status") == "旧版":
                warnings.append("旧版の資料です。最新版で同じ記載があるか確認してください。")
            if product_id and src.get("owner") != "自社" and src.get("product_id") not in (None, "", product_id):
                errors.append("対象製品と別の製品の資料です。")
            if seg.get("hidden_slide"):
                warnings.append("非表示スライドの記載です。")
            for c in detect_conditions(seg["text"]):
                warnings.append(f"箇所に「{c}」の記載があります。")
    elif ev.get("ref_type") == "utterance":
        rec, u = r.get("recording"), r.get("utterance")
        if not rec:
            errors.append(f"録画 {ev.get('rec_id')} が存在しません。")
        elif not u:
            errors.append(f"発言 {ev.get('utt_id')} が録画内に存在しません。")
        else:
            text = utt_text(u)
            if not quote.strip():
                errors.append("引用が空です。")
            elif norm(quote) not in norm(text) and norm(quote) not in norm(u.get("raw_text", "")):
                errors.append("引用が発言の文字起こしに見つかりません。")
            if not u.get("selected", True):
                errors.append("分析対象外（未選択）の発言です。")
            rng = rec.get("range") or {}
            if u.get("start") is not None and rng.get("end") is not None and (
                    u["start"] < rng.get("start", 0) or u["start"] > rng["end"]):
                errors.append("処理対象の時間範囲外の発言です。")
            if product_id and rec.get("product_id") not in (None, "", product_id):
                errors.append("対象製品と別の製品の録画です。")
            if not utt_confirmed(u):
                warnings.append("未確認の文字起こしです（確定した営業回答として扱えません）。")
            role = u.get("speaker_role") or "未分類"
            if role not in VENDOR_ROLES:
                warnings.append(f"発言者が「{role}」です。ベンダー側の説明・回答ではありません。")
            if u.get("utterance_type") in ("質問", "要望"):
                warnings.append(f"発言の種類が「{u['utterance_type']}」です。回答・確約ではありません。")
            if u.get("utterance_type") in ("将来予定", "未回答・調査中", "推測・未確定"):
                warnings.append(f"発言の種類が「{u['utterance_type']}」です。現在の機能・確定回答ではありません。")
            for c in detect_conditions(text):
                warnings.append(f"発言に「{c}」の表現があります。")
            if u.get("flags"):
                warnings.append("注意：" + "、".join(u["flags"]))
    elif ev.get("ref_type") == "answer":
        qq = r.get("question")
        if not qq:
            errors.append("質問が存在しません。")
        else:
            if norm(quote) not in norm(qq.get("answer_text", "")):
                errors.append("引用が回答本文に見つかりません。")
            if qq.get("status") != "回答確認済み":
                warnings.append("回答はまだ人が確認していません。")
    else:
        errors.append("根拠の種類が不明です。")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def evidence_fp(project: dict, ev: dict) -> str:
    """根拠の現在の状態の指紋。資料の版・本文・選択、発言の文章・話者・確認状態が変われば変化する。"""
    r = resolve(project, ev)
    if ev.get("ref_type") == "source":
        src, seg = r.get("source"), r.get("segment")
        latest = get_source(project, ev.get("source_id"))
        return fingerprint([seg and seg.get("text"), seg and seg.get("selected"), src and src.get("status"),
                            latest and latest.get("version")])
    if ev.get("ref_type") == "utterance":
        u = r.get("utterance")
        return fingerprint([u and utt_text(u), u and u.get("speaker_role"), u and u.get("speaker_name"),
                            u and u.get("speaker_confirmed"), u and u.get("review_status"),
                            u and u.get("utterance_type"), u and u.get("selected")])
    if ev.get("ref_type") == "answer":
        q = r.get("question")
        return fingerprint([q and q.get("answer_text"), q and q.get("status")])
    return fingerprint(ev)


def is_vendor_confirmed(project: dict, ev: dict) -> bool:
    """確定したベンダー説明として扱える発言か（話者・内容が人により確認済み、ベンダー側の回答）。"""
    if ev.get("ref_type") != "utterance":
        return False
    u = resolve(project, ev).get("utterance")
    return bool(u) and utt_confirmed(u) and (u.get("speaker_role") in VENDOR_ROLES) and u.get(
        "utterance_type") not in ("質問", "要望", "将来予定", "未回答・調査中", "推測・未確定")


def context_rows(project: dict, ev: dict, around: int = 2) -> list[dict]:
    """根拠の前後（同じスライド・ページ・シートの行、前後の発言）を返す。target=True が引用元。

    短い引用だけを切り出して意味を変えないよう、周辺の前提・例外・質問と回答を一緒に見せるために使う。
    """
    from ..media.subtitles import fmt_ts

    r = resolve(project, ev)
    rows = []
    if ev.get("ref_type") == "source" and r.get("segment"):
        segs = r["source"]["segments"]
        i = next(k for k, g in enumerate(segs) if g["seg_id"] == ev["seg_id"])
        grp = segs[i].get("group")
        for k in range(max(0, i - around), min(len(segs), i + around + 1)):
            g = segs[k]
            if grp and g.get("group") != grp:
                continue
            rows.append({"loc": g["loc_label"].split("」", 1)[-1].strip() or g["loc_label"], "text": g["text"],
                         "target": k == i, "note": "分析対象外" if not g.get("selected", True) else ""})
    elif ev.get("ref_type") == "utterance" and r.get("utterance"):
        utts = r["recording"]["utterances"]
        i = next(k for k, u in enumerate(utts) if u["id"] == ev["utt_id"])
        for k in range(max(0, i - around), min(len(utts), i + around + 1)):
            u = utts[k]
            who = u.get("speaker_role") or "未分類"
            rows.append({"loc": f"{fmt_ts(u.get('start'))} {who}", "text": utt_text(u), "target": k == i,
                         "note": "" if utt_confirmed(u) else "未確認"})
    elif ev.get("ref_type") == "answer" and r.get("question"):
        q = r["question"]
        rows = [{"loc": f"質問 {q['id']}", "text": q.get("question", ""), "target": False, "note": ""},
                {"loc": f"回答（{q.get('answer_source') or '回答元未記入'}）", "text": q.get("answer_text", ""),
                 "target": True, "note": ""}]
    return rows
