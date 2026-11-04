"""⑤ 導入判断：残った問題と根拠を確認し、人が導入するかを判断する。"""
from __future__ import annotations

import streamlit as st

from ...export.excel import report_workbook
from ..layout import header, next_button
from . import decision

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def render():
    p = header("decision", "導入判断",
               "診断結果（資料・説明上の見込み）と受入テストの結果、残った問題を確認して、導入するかを人が判断します。")
    if not p:
        return
    decision.decision_section(p, show_stats=True)
    st.download_button("導入確認レポート（Excel）をダウンロード", report_workbook(p), type="primary",
                       file_name=f"{p['project']['id']}_導入確認レポート.xlsx", mime=XLSX, icon=":material/download:")
    if p["project"].get("demo_id"):
        next_button("デモはここまでです。ホームへ（ほかのデモを見る）", "home")
