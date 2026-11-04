"""資料・発言からの関連箇所検索（軽量。ベクトルDBは使わない）。

日本語は2文字ずつの組（バイグラム）と英数字の単語で照合する。
「見つからない」は「機能がない」ではない。結果画面でも必ずそう表示する。
"""
from __future__ import annotations

import re
import unicodedata

from .logic.evidence import PLAN_WORDS, utt_text

_WORD = re.compile(r"[A-Za-z0-9]+")
_STOP = set("のをにはがでとてしたするいるあるこれそれためよう")


def _tokens(text: str) -> set[str]:
    t = unicodedata.normalize("NFKC", text or "").lower()
    words = set(_WORD.findall(t))
    jp = re.sub(r"[A-Za-z0-9\s、。・,.()（）「」『』:：|/\-]", "", t)
    grams = {jp[i:i + 2] for i in range(len(jp) - 1) if not (jp[i] in _STOP and jp[i + 1] in _STOP)}
    return words | grams


def requirement_query(req: dict) -> str:
    return " ".join(str(req.get(k, "")) for k in ("business", "workflow", "rules", "exceptions", "inputs",
                                                  "outputs", "original_text"))


def candidates(project: dict, req: dict, product_id: str | None, top_k: int = 8) -> list[dict]:
    """要件に関連しそうな箇所（資料の箇所・発言）を返す。分析対象に選ばれたものだけ。"""
    q = _tokens(requirement_query(req))
    if not q:
        return []
    scored = []
    for src in project.get("sources", []):
        if src.get("status") == "旧版":
            continue
        if src.get("owner") == "製品" and product_id and src.get("product_id") not in (None, "", product_id):
            continue
        segs = src.get("segments", [])
        for i, seg in enumerate(segs):
            if not seg.get("selected", True):
                continue  # 未選択（ノート・非表示スライド・対象外）は検索にも使わない
            s = len(q & _tokens(seg["text"]))
            if s >= 2:
                scored.append((s, {"ref_type": "source", "source_id": src["id"], "version": src["version"],
                                   "seg_id": seg["seg_id"], "text": seg["text"], "loc_label": seg["loc_label"],
                                   "source_name": src["name"], "group": seg.get("group"), "_idx": i,
                                   "_src": src}))
    for rec in project.get("recordings", []):
        if product_id and rec.get("product_id") not in (None, "", product_id):
            continue
        utts = rec.get("utterances", [])
        for i, u in enumerate(utts):
            if not u.get("selected", True):
                continue
            s = len(q & _tokens(utt_text(u)))
            if s >= 2:
                scored.append((s, {"ref_type": "utterance", "rec_id": rec["id"], "rec_version": rec.get("version", 1),
                                   "utt_id": u["id"], "text": utt_text(u), "_idx": i, "_rec": rec}))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:top_k]]


def with_context(hits: list[dict]) -> list[dict]:
    """ヒット箇所に、同じスライド・ページ・シートの周辺（前提・例外・プラン制限）と、前後の発言（質問と回答）を足す。"""
    out, seen = [], set()

    def add(item):
        key = (item.get("source_id") or item.get("rec_id"), item.get("seg_id") or item.get("utt_id"))
        if key in seen:
            return
        seen.add(key)
        out.append({k: v for k, v in item.items() if not k.startswith("_")})

    for h in hits:
        if h["ref_type"] == "source":
            src, i = h["_src"], h["_idx"]
            segs = src["segments"]
            for j in range(max(0, i - 2), min(len(segs), i + 3)):
                seg = segs[j]
                same_group = seg.get("group") == h.get("group")
                plan_hint = any(w in seg["text"] for w in PLAN_WORDS)
                if seg.get("selected", True) and (j == i or same_group or plan_hint):
                    add({"ref_type": "source", "source_id": src["id"], "version": src["version"],
                         "seg_id": seg["seg_id"], "text": seg["text"], "loc_label": seg["loc_label"],
                         "source_name": src["name"], "context_of": None if j == i else h["seg_id"]})
        else:
            rec, i = h["_rec"], h["_idx"]
            utts = rec["utterances"]
            for j in range(max(0, i - 2), min(len(utts), i + 3)):
                u = utts[j]
                if u.get("selected", True):
                    add({"ref_type": "utterance", "rec_id": rec["id"], "rec_version": rec.get("version", 1),
                         "utt_id": u["id"], "text": utt_text(u), "start": u.get("start"), "end": u.get("end"),
                         "speaker_role": u.get("speaker_role"), "speaker_confirmed": u.get("speaker_confirmed"),
                         "review_status": u.get("review_status"), "utterance_type": u.get("utterance_type"),
                         "meeting": rec.get("meeting_name"), "context_of": None if j == i else h["utt_id"]})
    return out
