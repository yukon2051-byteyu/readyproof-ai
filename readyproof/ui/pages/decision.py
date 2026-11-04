"""6 残った問題と導入判断。"""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from ...core import DECISIONS
from ...logic import metrics as M
from ...logic import rules
from ...logic.stale import decision_changed_since, decision_snapshot
from .. import state
from ..components import context_bar, page_title
from ..theme import category_chip, chip, esc, section, tiles

JUMP = {"自社に合うかを確認": "diagnosis", "質問・対応依頼": "questions", "試すこと・実施結果": "tests", "診断": "diagnosis",
        "テスト": "tests", "実施結果": "tests"}


def render():
    p = state.require_project()
    if not p:
        return
    context_bar("decision")
    page_title("6 残った問題と導入判断",
               "集計はプログラムで計算します。「資料・説明上の見込み」「人の確認」「実機テスト」「依頼の完了」は別々に数えます。")
    decision_section(p)


def decision_section(p, show_stats: bool = True):
    m = M.compute(p)
    if decision_changed_since(p):
        st.warning("導入判断の後に、診断・テスト・依頼などの関連情報が更新されています。判断を見直してください。")

    if not show_stats:
        return _issues_and_decision(p, m)
    section("資料・説明上の見込み（実機での確認ではありません）")
    st.markdown(" ".join(category_chip(c) + f"**{n}**　" for c, n in m["by_category"].items())
                + category_chip(None) + f"**{m['no_diagnosis']}**")
    tiles([
        {"label": "必須要件のうち、見込みが立っていない", "value": f"{len(m['must_unresolved'])}件",
         "note": f"必須 {m['must']}件中", "alert": bool(m["must_unresolved"])},
        {"label": "診断を人が確認した割合", "value": m["diag_reviewed"]["text"], "note": "分母：診断済みの要件"},
        {"label": "根拠に矛盾", "value": f"{m['contradictions']}件", "note": "書面での確認が必要",
         "alert": bool(m["contradictions"])},
        {"label": "情報不足・ベンダー確認", "value": f"{m['lack_info']}件", "note": "質問で解消する"},
    ])
    section("実機テスト（人が実際に試した結果）", gold=True)
    tiles([
        {"label": "合格率", "value": m["pass_rate"]["text"], "gold": True, "note": "分母：合否を判定した最新結果"},
        {"label": "実施済み", "value": m["executed_rate"]["text"], "gold": True, "note": "分母：有効なテスト全件"},
        {"label": "不合格", "value": f"{len(m['failed'])}件", "gold": True, "note": "依頼書で対応", "alert": bool(m["failed"])},
        {"label": "未実施", "value": f"{len(m['not_run'])}件", "gold": True, "note": "実施不能は別に数える"},
        {"label": "必須要件のうち、実機で未確認", "value": f"{len(m['must_not_verified'])}件",
         "gold": True, "note": f"必須 {m['must']}件中", "alert": bool(m["must_not_verified"])},
    ])
    section("質問・依頼")
    tiles([
        {"label": "未回答の質問", "value": f"{len(m['unanswered'])}件"},
        {"label": "回答の確認待ち", "value": f"{len(m['answer_unreviewed'])}件"},
        {"label": "未確定の依頼書", "value": f"{len(m['cr_draft'])}件"},
        {"label": "対応中の依頼", "value": f"{len(m['cr_active'])}件"},
        {"label": "再確認が必要", "value": f"{len(m['stale'])}件", "note": "古い根拠・旧版に基づく結果",
         "alert": bool(m["stale"])},
    ])

    _issues_and_decision(p, m)


def _issues_and_decision(p, m):
    issues = M.remaining_issues(p, m)
    section(f"残った問題（{len(issues)}件・すべて表示）")
    if issues:
        df = pd.DataFrame(issues)
        ev = st.dataframe(df, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                          key="issue_table", height=min(420, 38 + 35 * len(df)))
        if ev.selection.rows:
            it = issues[ev.selection.rows[0]]
            if st.button(f"{it['ID']} の画面へ移動", icon=":material/arrow_forward:"):
                target = JUMP.get(it["次の操作"], "diagnosis")
                if target == "diagnosis" and it["ID"].startswith("REQ"):
                    st.session_state.sel_diag_req = it["ID"]
                if target == "tests" and it["ID"].startswith("T-"):
                    st.session_state.sel_test = it["ID"]
                    st.session_state.test_filter_req = "すべて"
                if target == "questions":
                    st.session_state._goto_qview = "依頼書" if it["ID"].startswith("CR") else "質問"
                state.goto(target)
    else:
        st.success("残った問題はありません（未登録の要件・テストがないかも確認してください）。")

    st.divider()
    d = p["decision"]
    section("導入判断（人が判断します）")
    if d["value"] != "未判断":
        st.markdown(f"{chip('現在の判断：' + d['value'], 'ok' if d['value'] == '導入可' else ('warn' if d['value'] == '条件付き導入可' else 'bad'))}"
                    f"<span class='rp-small'>{esc(d['by'])}（自己申告）／{esc(d['date'])}／理由：{esc(d['reason'])}"
                    f"{'／条件：' + esc(d['conditions']) if d['conditions'] else ''}</span>", unsafe_allow_html=True)
    with st.form("form_decision"):
        val = st.radio("判断", DECISIONS, index=DECISIONS.index(d["value"]), horizontal=True)
        c1, c2 = st.columns(2)
        by = c1.text_input("判断者", value=d["by"] or state.user_name())
        dt = c2.date_input("日付", value=date.today())
        reason = st.text_area("理由", value=d["reason"], height=70)
        cond = st.text_area("条件（条件付き導入可の場合は必須）", value=d["conditions"], height=60)
        st.caption(f"判断時点の残件 {len(issues)} 件も一緒に記録します。認証がないため、名前は本人確認・正式な承認ではありません。")
        if st.form_submit_button("判断を記録", type="primary"):
            try:
                rules.record_decision(p, val, by, str(dt), reason, cond, decision_snapshot(p, {**{
                    k: (len(v) if isinstance(v, list) else v) for k, v in m.items() if k not in ("by_category", "diag_reviewed",
                                                                                                    "pass_rate", "executed_rate")},
                    "remaining": len(issues)}))
                st.rerun()
            except rules.RuleError as e:
                st.error(str(e))
    if d.get("history"):
        with st.expander(f"過去の判断（{len(d['history'])}件）"):
            st.dataframe(pd.DataFrame(d["history"]), hide_index=True)
