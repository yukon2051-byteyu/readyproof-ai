"""③ 診断結果（出力1）：要件ごとに「そのまま使えるか」を、根拠（元資料の前後と引用）と一緒に示す。

不明点はその場でベンダーへの質問に、合わない部分は対応方法と依頼書につなげる。
"""
from __future__ import annotations

import streamlit as st

from ...core import ACTION_TYPES, DIAG_CATEGORIES
from ...export.excel import questionnaire_workbook
from ...logic import rules
from .. import state
from ..components import evidence_view
from ..layout import header, next_button
from ..theme import CATEGORY_STYLE, badge, box, category_chip, chip, esc, review_chip, section, tiles
from . import diagnosis, questions

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
COLOR = {"green": "#1E7B45", "orange": "#B45309", "red": "#B42318", "gray": "#5B6574", "violet": "#6B3FA0"}
# 画面で使う短い言葉（区分そのものは変えない）
PLAIN = {
    "そのまま対応できる見込み": "そのまま使える見込み",
    "標準設定で対応できる見込み": "設定すれば使える見込み",
    "追加対応の検討が必要": "追加の対応が必要",
    "対応不可との記載・確認済み発言あり": "使えない（記載・確認あり）",
    "情報不足・ベンダー確認が必要": "確認が必要（情報不足）",
    "根拠間に矛盾あり": "確認が必要（根拠が矛盾）",
}


def render():
    p = header("result", "診断結果",
               "自社の要件ごとに、製品がそのまま使えるかを判定しました。これは資料・営業説明から見た「見込み」です。実際に動くかは④の受入テストで確かめます。")
    if not p:
        return
    reqs = [r for r in p["requirements"] if r["status"] != "廃止"]
    if not reqs:
        st.info("まだ自社の要件がありません。② 自社のルールで作ってください。")
        if st.button("② 自社のルールへ"):
            state.goto("input2")
        return
    summary(p, reqs)
    if st.toggle("AIで診断を作る・作り直す", key="show_ai_diag"):
        with box():
            diagnosis.ai_section(p, reqs)
    focus = st.session_state.get("focus_req")
    section("要件ごとの診断")
    for r in reqs:
        card(p, r, focus == r["id"])
    st.download_button("ベンダーへの質問書（Excel）をダウンロード", questionnaire_workbook(p),
                       file_name=f"{p['project']['id']}_質問書.xlsx", mime=XLSX, icon=":material/download:")
    next_button("次へ：④ 受入テスト書", "tests")


def summary(p, reqs):
    must = [r for r in reqs if r["priority"] == "必須"]
    cnt = {c: 0 for c in DIAG_CATEGORIES}
    none = 0
    for r in must:
        dg = rules.current_diagnosis(p, r["id"])
        if dg:
            cnt[dg["category"]] += 1
        else:
            none += 1
    check = cnt["情報不足・ベンダー確認が必要"] + cnt["根拠間に矛盾あり"]
    st.markdown(f"**必須の要件 {len(must)}件の判定**（そのほかの要件 {len(reqs) - len(must)}件は下の一覧にあります）")
    tiles([
        {"label": "そのまま使える見込み", "value": f"{cnt[DIAG_CATEGORIES[0]]}件", "color": COLOR["green"]},
        {"label": "設定すれば使える見込み", "value": f"{cnt[DIAG_CATEGORIES[1]]}件", "color": COLOR["green"]},
        {"label": "追加の対応が必要", "value": f"{cnt[DIAG_CATEGORIES[2]]}件", "color": COLOR["orange"]},
        {"label": "使えない（記載・確認あり）", "value": f"{cnt[DIAG_CATEGORIES[3]]}件", "color": COLOR["red"]},
        {"label": "確認が必要（情報不足・矛盾）", "value": f"{check}件", "color": COLOR["violet"]},
        {"label": "まだ診断していない", "value": f"{none}件", "color": COLOR["gray"]},
    ])


def card(p, r, focused: bool):
    dg = rules.current_diagnosis(p, r["id"])
    with box():
        c1, c2 = st.columns([5, 1.5], vertical_alignment="top")
        if dg:
            color, icon = CATEGORY_STYLE.get(dg["category"], ("gray", None))
            head = badge(PLAIN.get(dg["category"], dg["category"]), color, icon) + review_chip(dg["review_status"], dg["origin"])
        else:
            head = badge("まだ診断していない", "gray", "hourglass_empty")
        c1.markdown(f"{head}{chip(r['priority'], 'info')}<br><span class='rp-item'><span class='h'>{esc(r['id'])}　"
                    f"{esc(r['business'])}</span></span>　<span class='rp-small'>{esc(r['rules'] or r['workflow'])}</span>",
                    unsafe_allow_html=True)
        nq = sum(1 for q in p["questions"] if r["id"] in q.get("req_ids", []))
        ncr = sum(1 for c in p["requests"] if r["id"] in c.get("req_ids", []))
        c1.caption(f"理由：{dg['reason']}" if dg else "資料・営業説明と照合して、判定を作ってください（上の「AIで診断を作る」または詳しく確認する）。")
        if c2.button("閉じる" if focused else "詳しく確認する", key=f"fr_{r['id']}", width="stretch",
                     type="secondary" if focused else "primary"):
            st.session_state.focus_req = None if focused else r["id"]
            st.rerun()
        c2.caption(f"根拠 {len(dg['evidence']) if dg else 0}件・質問 {nq}件・依頼 {ncr}件")
        if not focused:
            if dg and dg["evidence"]:
                evidence_view(p, dg["evidence"][0], state.product_id())
                if len(dg["evidence"]) > 1:
                    st.caption(f"ほかの根拠 {len(dg['evidence']) - 1}件は「詳しく確認する」で表示します。")
            return
        st.divider()
        diagnosis.detail(p, r)
        followups(p, r, dg)


def followups(p, r, dg):
    section("ベンダーへの質問")
    qs = [q for q in p["questions"] if r["id"] in q.get("req_ids", [])]
    for q in qs:
        with box():
            questions.question_detail(p, q)
    if st.button("この要件について質問を作る", key=f"mkq_{r['id']}", icon=":material/help:"):
        rem = "、".join(dg["remaining_conditions"]) if dg and dg["remaining_conditions"] else "設定方法・対象プラン・追加費用の有無"
        q = rules.add_question(p, {"req_ids": [r["id"]], "diag_id": dg["id"] if dg else "",
                                   "background": f"自社の要件「{r['business']}」：{r['rules']}",
                                   "question": f"この要件について、次の点を教えてください：{rem}",
                                   "points": "・対応できるか\n・対象プラン・オプション\n・設定方法\n・追加費用の有無"})
        state.flash(f"{q['id']}（下書き）を作りました。内容を直して確定してください。")
        st.rerun()

    if not dg or dg["category"] in DIAG_CATEGORIES[:2]:
        if not [a for a in p["actions"] if a["req_id"] == r["id"]]:
            return
    section("合わない部分への対応と依頼書")
    for a in [a for a in p["actions"] if a["req_id"] == r["id"]]:
        tone = {"採用": "ok", "不採用": "muted", "候補": "info"}[a["status"]]
        cc1, cc2 = st.columns([4, 2], vertical_alignment="center")
        cc1.markdown(f"{chip(a['status'], tone)}{chip(a['type'], 'info')}{esc(a['reason'])}"
                     + (f"<br><span class='rp-small'>不明点：{esc(a['unknowns'])}</span>" if a["unknowns"] else ""),
                     unsafe_allow_html=True)
        if a["status"] == "候補":
            why = cc2.text_input("判断の理由", key=f"aw_{a['id']}", label_visibility="collapsed", placeholder="判断の理由")
            b1, b2 = cc2.columns(2)
            for col, val in ((b1, "採用"), (b2, "不採用")):
                if col.button(val, key=f"ad_{a['id']}_{val}", width="stretch"):
                    try:
                        rules.decide_action(p, a, val, state.user_name(), why)
                        st.rerun()
                    except rules.RuleError as e:
                        st.error(str(e))
        else:
            cc2.caption(f"{a['decided_by']}（自己申告）：{a['decision_reason']}")
    with st.form(f"form_act_{r['id']}", clear_on_submit=True):
        f1, f2 = st.columns([1, 2])
        typ = f1.selectbox("対応方法の候補を追加", ACTION_TYPES)
        reason = f2.text_input("内容と理由（費用・期間は想像で書かない）")
        if st.form_submit_button("候補に追加"):
            rules.add_action(p, {"req_id": r["id"], "diag_id": dg["id"] if dg else "", "type": typ, "reason": reason})
            st.rerun()
    for c in [c for c in p["requests"] if r["id"] in c.get("req_ids", [])]:
        with box():
            questions.request_detail(p, c)
    if st.button("この要件の依頼書を作る（下書き）", key=f"mkcr_{r['id']}", icon=":material/edit_note:"):
        kind = "調査依頼" if dg and dg["category"] not in DIAG_CATEGORIES[2:4] else "改修依頼"
        c = rules.add_request(p, {"title": f"{r['business']}への対応", "kind": kind, "phase": "資料診断段階の懸念",
                                  "req_ids": [r["id"]], "diag_ids": [dg["id"]] if dg else [],
                                  "background": dg["reason"] if dg else "", "needed_behavior": r["rules"],
                                  "acceptance_criteria": r["rules"], "priority": "中"})
        state.flash(f"{c['id']}（下書き）を作りました。内容を直して確定してください。")
        st.rerun()
