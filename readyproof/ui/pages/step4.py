"""④ 受入テスト（出力2）：テストを作って確定し、人が実機で試した結果を記録して、受入テストを出力する。"""
from __future__ import annotations

import streamlit as st

from ...export.excel import acceptance_test_workbook
from ...logic import metrics as M
from ...logic import rules
from ...logic.stale import run_stale_reasons, test_stale_reasons
from .. import readonly, state
from ..layout import header, next_button
from ..theme import RESULT_TONE, badge, box, chip, esc, section, tiles
from . import tests

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def render():
    p = header("tests", "受入テスト",
               "自社の要件を満たすかを、実際の製品で人が試すためのテストです。テストを確定し、試した結果を記録すると、受入テスト仕様書 兼 成績書（Excel）に反映されます。")
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
    st.download_button("受入テスト仕様書・成績書（Excel）をダウンロード", acceptance_test_workbook(p), type="primary",
                       file_name=f"{p['project']['id']}_受入テスト仕様書・成績書.xlsx", mime=XLSX, icon=":material/download:")
    if not state.is_demo():
        ai_tests_box(p)

    focus = st.session_state.get("sel_test")
    for req in [r for r in p["requirements"] if r["status"] != "廃止"]:
        rts = [t for t in ts if req["id"] in t["req_ids"]]
        section(f"{req['id']}　{req['business']}（テスト {len(rts)}件）")
        if not rts:
            st.caption("この要件のテストはまだありません。")
        for t in rts:
            row(p, t, focus == t["id"])

    next_button("次へ：⑤ 導入判断", "decision")


def ai_tests_box(p):
    """テスト仕様は常にAIで作る。テストがない要件があれば実行欄を表示、なければ「追加で作る」だけ表示。"""
    s = state.settings()
    confirmed = [r for r in p["requirements"] if r["status"] == "確定"]
    if not confirmed:
        st.caption("確定した要件がありません。② 自社のルールで要件を確定すると、テスト仕様を作れます。")
        return
    notest = [r["id"] for r in confirmed
              if not any(r["id"] in t["req_ids"] and t["status"] != "廃止" for t in p["tests"])]
    if notest:
        _ai_tests(p, s, confirmed, notest, f"AIでテスト仕様を作る（テストがない要件 {len(notest)}件）", "AIでテスト仕様を作る")
    elif st.session_state.get("more_tests"):
        _ai_tests(p, s, confirmed, [], "AIでテスト仕様を追加で作る", "AIでテスト仕様を追加で作る")
    elif st.button("AIでテスト仕様を追加で作る", icon=":material/playlist_add:", key="more_tests_open"):
        st.session_state.more_tests = True
        st.rerun()


def _ai_tests(p, s, confirmed, default, title, label):
    from ...ai.tasks import build_tests_input, run_tests_multi
    from ..components import ai_panel, run_ai

    with box():
        section(title)
        st.caption("作ったテストは下書きです。人が手順と期待結果を確認して確定します。すでにあるテストは上書きしません。")
        ids = [r["id"] for r in confirmed]
        lim = s.limits.max_requirements_per_diagnosis
        sel = st.multiselect(f"対象の要件（確定済み・1回最大{lim}件・テストは合計最大{s.limits.max_tests_per_generation}件）",
                             ids, default=default[:lim], max_selections=lim, key=f"form_ai_tests_{label}")
        if sel:
            client = ai_panel(f"tests_{label}", f"{len(sel)}件の要件のテスト仕様", build_tests_input(p, sel), 16000,
                              ["要件・診断の要点・受入条件"], button_label=label)
            if client:
                run_ai(lambda: run_tests_multi(p, sel, client, s, state.ledger(), st.session_state.get("access_code", "")),
                       "{n}件のテスト仕様（下書き）を作りました。手順と期待結果を確認して確定してください。")
        if not default and st.button("追加で作らない", key="more_tests_close", type="tertiary"):
            st.session_state.more_tests = False
            st.rerun()


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
        open_label = "詳しく見る" if state.is_demo() else "開く・結果を記録"
        if c2.button("閉じる" if opened else open_label, key=f"ot_{t['id']}", width="stretch"):
            st.session_state.sel_test = None if opened else t["id"]
            st.rerun()
        if opened:
            st.divider()
            with readonly.scope(state.is_demo()):  # デモは見るだけ（編集・確定・結果の記録は押せない）
                tests.detail(p, t)
