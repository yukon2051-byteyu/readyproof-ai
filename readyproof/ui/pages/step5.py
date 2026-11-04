"""⑤ 導入判断：残った問題と根拠を確認し、人が導入するかを判断する。"""
from __future__ import annotations

import streamlit as st

from ...export.excel import report_workbook
from .. import state
from ..layout import header
from . import decision

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def render():
    p = header("decision", "導入判断",
               "診断結果（資料・説明上の見込み）と受入テストの結果、残った問題を確認して、導入するかを人が判断します。")
    if not p:
        return
    decision.decision_section(p, show_stats=True)
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    c1, _, c2 = st.columns([1.7, 0.7, 1.4], vertical_alignment="top")  # 2つのボタンを上揃え
    c1.download_button("導入確認レポート（Excel）をダウンロード", report_workbook(p), type="primary",
                       file_name=f"{p['project']['id']}_導入確認レポート.xlsx", mime=XLSX, icon=":material/download:",
                       width="stretch")
    if p["project"].get("demo_id") and c2.button("デモはここまでです。ホームへ  \n（ほかのデモを見る）", type="primary",
                                                 icon=":material/arrow_forward:", width="stretch", key="next_home"):
        state.goto("home")
