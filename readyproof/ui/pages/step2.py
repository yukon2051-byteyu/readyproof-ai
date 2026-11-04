"""② 自社のルール（入力2）：質問に答えて要件を作り、確認・確定する。"""
from __future__ import annotations

import os

import streamlit as st

from ...ingest import IngestError, ingest_bytes
from ...logic import rules
from .. import readonly, state
from ..components import name_required
from ..layout import header, next_button
from ..theme import badge, box, chip, esc, section
from . import requirements


def render():
    p = header("input2", "自社のルール",
               "質問に答えると、自社の業務ルールを「要件」にまとめます。分からない点は「分からない・未定」で大丈夫です（推測では埋めません）。")
    if not p:
        return
    reqs = [r for r in p["requirements"] if r["status"] != "廃止"]
    if state.is_demo():  # デモは見るだけ
        req_cards(p, reqs, ro=True)
        next_button("次へ：③ 診断結果", "result")
        return
    busy = st.session_state.get("intake_i", 0) > 0 or bool((st.session_state.get("aiq") or {}).get("questions"))
    show = not reqs or st.toggle("質問に答えて要件を追加する", key="show_intake", value=busy)
    if show:
        has_docs = any(s["owner"] == "製品" for s in p["sources"]) or p["recordings"]
        modes = ["AIが製品の資料を踏まえて質問する（料金あり）", "決まった質問に答える（料金なし）"]
        mode = st.radio("聞き方", modes, index=0 if has_docs else 1, horizontal=True, key="intake_mode")
        if mode == modes[0]:
            if not has_docs:
                st.info("先に ① 製品の資料で、製品の資料か録画を読み込んでください。AIはその内容を踏まえて質問します。")
            else:
                requirements.ai_interview_view(p)
        else:
            st.caption("聞くこと：① 業務の種類 ② 必ず守るルール（金額・期限・禁止事項） ③ 例外・未定のこと "
                       "④ 誰が使うか・権限 ⑤ 使うときの条件（予算・プラン・連携・端末・通信）")
            requirements.intake_view(p)

    req_cards(p, reqs)

    section("ほかの入れ方")
    if st.toggle("規程・手順書のファイルから作る", key="show_owndoc"):
        f = st.file_uploader("自社の規程・手順書（PDF・Word・Excel・PowerPoint・テキスト）",
                             type=["pdf", "docx", "xlsx", "pptx", "txt"], key="own_doc")
        if f is not None and st.button("読み込む", key="own_doc_go"):
            try:
                res = ingest_bytes(f.name, f.getvalue(), state.settings().limits)
                src = rules.add_source(p, res.to_dict(), {"file_name": f.name, "name": os.path.splitext(f.name)[0],
                                                          "owner": "自社", "kind": "その他"})
                st.success(f"{src['id']} として読み込みました。下の「文章から要件を作る（AI）」で要件にできます。")
            except IngestError as e:
                st.error(str(e))
        requirements.ai_split(p)
    if st.toggle("1件ずつ手で入力する", key="show_manual"):
        requirements.add_manual(p)
    next_button("次へ：③ 診断結果", "result")


def req_cards(p, reqs, ro: bool = False):
    drafts = [r for r in reqs if r["status"] == "下書き"]
    section(f"自社の要件（{len(reqs)}件・確定 {len(reqs) - len(drafts)}件）")
    if not reqs:
        st.info("まだ要件がありません。上の質問に答えて、要件を作ってください。")
        return
    ready = [r for r in drafts if not r.get("open_issues") and not r.get("term_warnings")]
    if ready and not ro:  # デモでは一括確定ボタン自体を出さない
        if st.button(f"未確定事項のない下書き {len(ready)}件をまとめて確定する", icon=":material/done_all:"):
            by = name_required()
            if by:
                for r in ready:
                    rules.confirm_requirement(p, r, by)
                st.rerun()
    edit = st.session_state.get("edit_req")
    for r in reqs:
        with box():
            c1, c2 = st.columns([5, 1.6], vertical_alignment="center")
            st_badge = badge("確定", "green", "check") if r["status"] == "確定" else badge("下書き", "gray", "edit_note")
            c1.markdown(f"{st_badge}{chip(r['priority'], 'info')}<span class='rp-item'><span class='h'>"
                        f"{esc(r['id'])}　{esc(r['business'])}</span></span><br>{esc(r['rules'] or r['workflow'])}"
                        + (f"<br><span style='color:#B45309'>未確定：{esc(r['open_issues'])}</span>" if r.get("open_issues") else ""),
                        unsafe_allow_html=True)
            if ro:  # デモ：確定・編集ボタンは押せない状態で表示
                with readonly.scope(True):
                    b1, b2 = c2.columns(2)
                    if r["status"] == "下書き":
                        b1.button("確定", key=f"cf_{r['id']}", type="primary", width="stretch")
                    b2.button("編集", key=f"ed_{r['id']}", width="stretch")
                continue
            b1, b2 = c2.columns(2)
            if r["status"] == "下書き" and b1.button("確定", key=f"cf_{r['id']}", type="primary", width="stretch"):
                by = name_required()
                if by:
                    try:
                        rules.confirm_requirement(p, r, by)
                        st.rerun()
                    except rules.RuleError as e:
                        st.error(str(e))
            if b2.button("閉じる" if edit == r["id"] else "編集", key=f"ed_{r['id']}", width="stretch"):
                st.session_state.edit_req = None if edit == r["id"] else r["id"]
                st.rerun()
            if edit == r["id"]:
                st.session_state.sel_req = r["id"]
                requirements.detail(p)
