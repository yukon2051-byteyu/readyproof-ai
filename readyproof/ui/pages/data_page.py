"""保存（JSON）・読込・Excel 出力・デモの初期化。"""
from __future__ import annotations

import copy

import pandas as pd
import streamlit as st

from ...export.excel import questionnaire_workbook, report_workbook, request_workbook
from ...export.jsonio import LoadError, content_summary, from_json_bytes, to_json_bytes
from .. import state
from ..components import context_bar, page_title

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def render():
    p = state.project()
    context_bar("")
    page_title("保存・Excel出力", "案件はJSONで保存し、後で読み込んで再開できます。Excelは社内共有・ベンダー送付用です。")
    if p:
        pid = p["project"]["id"]
        st.markdown("**Excel出力**")
        c1, c2 = st.columns(2)
        c1.download_button("適合性・導入確認レポート", report_workbook(p), file_name=f"{pid}_導入確認レポート.xlsx", mime=XLSX,
                           icon=":material/download:", type="primary")
        c2.download_button("ベンダーへの質問書", questionnaire_workbook(p), file_name=f"{pid}_質問書.xlsx", mime=XLSX,
                           icon=":material/download:")
        if p["requests"]:
            cid = st.selectbox("依頼書（1件ずつ出力）", [c["id"] for c in p["requests"]],
                               format_func=lambda i: f"{i}：{next(c['title'] for c in p['requests'] if c['id'] == i)}")
            st.download_button("この依頼書を出力", request_workbook(p, cid), file_name=f"{cid}_依頼書.xlsx", mime=XLSX,
                               icon=":material/download:")
        st.divider()
        st.markdown("**案件をJSONで保存**")
        st.dataframe(pd.DataFrame(content_summary(p)), hide_index=True, width="stretch")
        c1, c2 = st.columns(2)
        notes = c1.checkbox("未選択の発表者ノートの本文も保存する", value=False)
        utts = c2.checkbox("分析対象外にした発言の本文も保存する", value=True)
        st.caption("JSONには資料・録画の元ファイル（バイナリ）は含まれません。APIキーや利用コードも含まれません。")
        st.download_button("JSONを保存", to_json_bytes(p, notes, utts), file_name=f"{pid}_readyproof.json",
                           mime="application/json", icon=":material/save:")
        if p["project"].get("demo_id") and st.session_state.get("demo_initial"):
            st.divider()
            if st.button("デモを初期状態に戻す", icon=":material/restart_alt:"):
                state.set_project(copy.deepcopy(st.session_state.demo_initial), demo_initial=st.session_state.demo_initial)
                state.flash("デモを初期状態に戻しました。")
                st.rerun()
    else:
        st.info("案件が開かれていません。保存済みのJSONを読み込めます。")
    st.divider()
    st.markdown("**保存した案件を読み込む**")
    up = st.file_uploader("JSONファイル", type=["json"], key="data_load")
    if up is not None and st.button("読み込む（現在の案件と置き換え）"):
        try:
            newp = from_json_bytes(up.getvalue())
        except LoadError as e:
            st.error(f"読み込めませんでした：{e}（現在の作業はそのままです）")
        else:
            state.set_project(newp)
            state.flash("読み込みました。")
            st.rerun()
