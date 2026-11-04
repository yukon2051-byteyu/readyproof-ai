"""④ 受入テスト（出力2）：テストを作って確定し、人が実機で試した結果を記録して、受入テストを出力する。"""
from __future__ import annotations

import streamlit as st

from ...export.excel import acceptance_test_workbook, report_workbook
from ...logic import metrics as M
from ...logic import rules
from ...logic.stale import run_stale_reasons, test_stale_reasons
from ...testgen import draft_tests
from .. import state
from ..layout import header
from ..theme import RESULT_TONE, badge, box, chip, esc, section, tiles
from . import decision, tests

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def render():
    p = header("tests", "受入テスト",
               "自社の要件を満たすかを、実際の製品で人が試すためのテストです。テストを確定し、試した結果を記録すると、受入テスト仕様書（Excel）に反映されます。")
    if not p:
        return
    ts = [t for t in p["tests"] if t["status"] != "廃止"]
    m = M.compute(p)
    tiles([
        {"label": "テスト", "value": f"{len(ts)}件", "note": f"確定 {sum(1 for t in ts if t['status'] == '確定')}件"},
        {"label": "合格", "value": f"{len(m['passed'])}件", "color": "#1E7B45"},
        {"label": "不合格", "value": f"{len(m['failed'])}件", "color": "#B42318", "alert": bool(m["failed"])},
        {"label": "まだ試していない", "value": f"{len(m['not_run'])}件", "color": "#5B6574"},
        {"label": "試せなかった", "value": f"{len(m['blocked'])}件", "note": "合否には数えない", "color": "#B45309"},
    ])
    c1, c2, c3 = st.columns([1.3, 1.3, 1])
    c1.download_button("受入テスト仕様書（Excel）をダウンロード", acceptance_test_workbook(p), type="primary",
                       file_name=f"{p['project']['id']}_受入テスト仕様書.xlsx", mime=XLSX, icon=":material/download:",
                       width="stretch")
    if c2.button("確定した要件からテスト仕様を作る（AIなし）", icon=":material/playlist_add:", width="stretch"):
        made = draft_tests(p)
        state.flash(f"{len(made)}件のテスト仕様を作りました（下書き）。画面の場所を製品で確かめ、期待結果を確認してから確定してください。"
                    if made else "新しく作るテストはありません（確定した要件には、すでにテストがあります）。")
        st.rerun()
    c3.download_button("導入確認レポート", report_workbook(p), file_name=f"{p['project']['id']}_導入確認レポート.xlsx",
                       mime=XLSX, icon=":material/description:", width="stretch")
    if not st.session_state.get("tour") and st.toggle("AIでテスト仕様を作る", key="show_ai_tests"):
        with box():
            reqs = [r for r in p["requirements"] if r["status"] == "確定"]
            if reqs:
                st.session_state.test_filter_req = st.selectbox("対象の要件", [r["id"] for r in reqs], key="ai_t_req")
                tests.ai_gen(p, reqs, st.session_state.test_filter_req)

    focus = st.session_state.get("sel_test")
    for req in [r for r in p["requirements"] if r["status"] != "廃止"]:
        rts = [t for t in ts if req["id"] in t["req_ids"]]
        section(f"{req['id']}　{req['business']}（テスト {len(rts)}件）")
        if not rts:
            st.caption("この要件のテストはまだありません。")
        for t in rts:
            row(p, t, focus == t["id"])

    section("残った問題と導入判断")
    decision.decision_section(p, show_stats=False)


def row(p, t, opened: bool):
    lr = rules.latest_run(p, t["id"])
    label = (lr["result"] if lr["status"] == "完了" else lr["status"]) if lr else "未実施"
    stale = bool(test_stale_reasons(p, t) or (lr and run_stale_reasons(p, lr)))
    with box():
        c1, c2 = st.columns([5, 1.3], vertical_alignment="center")
        state_b = badge("確定", "green", "check") if t["status"] == "確定" else badge("下書き", "gray", "edit_note")
        c1.markdown(chip(label, RESULT_TONE.get(label, "muted")) + state_b + (chip("再確認が必要", "bad") if stale else "")
                    + f"<span class='rp-item'><span class='h'>{esc(t['id'])}　{esc(t['title'])}</span></span><br>"
                    f"<span class='rp-small'>{esc(t['viewpoint'])}／期待結果：{esc(t['expected'][:80])}</span>",
                    unsafe_allow_html=True)
        if c2.button("閉じる" if opened else "開く・結果を記録", key=f"ot_{t['id']}", width="stretch"):
            st.session_state.sel_test = None if opened else t["id"]
            st.rerun()
        if opened:
            st.divider()
            tests.detail(p, t)
