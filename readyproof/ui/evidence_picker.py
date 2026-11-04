"""根拠を手動で選ぶ部品（資料の箇所／発言／ベンダー回答）。"""
from __future__ import annotations

import streamlit as st

from ..logic.evidence import utt_confirmed, utt_text
from ..media.subtitles import fmt_ts


def pick(p: dict, key: str, allow=("source", "utterance", "answer")) -> dict | None:
    """選択中の根拠を返す（ボタンは呼び出し側）。引用は原文から必要部分だけを残して使う。"""
    kinds = {"source": "資料の箇所", "utterance": "録画の発言", "answer": "ベンダー回答"}
    opts = [k for k in allow if (k != "utterance" or p["recordings"]) and (k != "answer" or any(
        q.get("answer_text") for q in p["questions"]))]
    if not opts:
        st.caption("根拠に使える資料・発言・回答がありません。")
        return None
    t = st.radio("根拠の種類", opts, format_func=lambda k: kinds[k], horizontal=True, key=f"{key}_type")
    if t == "source":
        srcs = [s for s in p["sources"] if s["status"] != "旧版"]
        if not srcs:
            st.caption("有効な資料がありません。")
            return None
        si = st.selectbox("資料", range(len(srcs)), key=f"{key}_src",
                          format_func=lambda i: f"{srcs[i]['id']} 第{srcs[i]['version']}版：{srcs[i]['name']}（{srcs[i]['owner']}）")
        src = srcs[si]
        segs = [g for g in src["segments"] if g.get("selected")]
        if not segs:
            st.caption("分析対象に選ばれた箇所がありません。")
            return None
        gi = st.selectbox("箇所（分析対象のみ）", range(len(segs)), key=f"{key}_seg",
                          format_func=lambda i: f"{segs[i]['loc_label']}：{segs[i]['text'][:50]}")
        seg = segs[gi]
        quote = st.text_area("引用（原文から必要な部分だけ残す。言い換えない）", value=seg["text"], height=70,
                             key=f"{key}_quote_{src['id']}_{seg['seg_id']}")
        kind = "自社資料" if src["owner"] == "自社" else ("ベンダー回答" if src["kind"] == "質問と回答" else "資料の記載")
        return {"ref_type": "source", "source_id": src["id"], "version": src["version"], "seg_id": seg["seg_id"],
                "quote": quote.strip(), "kind": kind}
    if t == "utterance":
        recs = p["recordings"]
        ri = st.selectbox("録画", range(len(recs)), key=f"{key}_rec",
                          format_func=lambda i: f"{recs[i]['id']}：{recs[i].get('meeting_name') or recs[i].get('file_name')}")
        rec = recs[ri]
        utts = [u for u in rec["utterances"] if u.get("selected", True)]
        if not utts:
            return None
        ui = st.selectbox("発言（分析対象のみ）", range(len(utts)), key=f"{key}_utt",
                          format_func=lambda i: f"{fmt_ts(utts[i].get('start'))} {utts[i].get('speaker_role')}"
                                                f"{'・確認済み' if utt_confirmed(utts[i]) else '・未確認'}：{utt_text(utts[i])[:40]}")
        u = utts[ui]
        if not utt_confirmed(u):
            st.warning("未確認の文字起こしです。根拠にできますが、確定した営業回答としては扱われません。")
        quote = st.text_area("引用", value=utt_text(u), height=60, key=f"{key}_uq_{rec['id']}_{u['id']}")
        return {"ref_type": "utterance", "rec_id": rec["id"], "rec_version": rec.get("version", 1), "utt_id": u["id"],
                "quote": quote.strip(), "kind": "営業・ベンダーの説明"}
    qs = [q for q in p["questions"] if q.get("answer_text")]
    qi = st.selectbox("回答", range(len(qs)), key=f"{key}_q",
                      format_func=lambda i: f"{qs[i]['id']}（{qs[i]['status']}）：{qs[i]['answer_text'][:40]}")
    q = qs[qi]
    quote = st.text_area("引用", value=q["answer_text"], height=60, key=f"{key}_aq_{q['id']}")
    return {"ref_type": "answer", "question_id": q["id"], "quote": quote.strip(), "kind": "ベンダー回答"}
