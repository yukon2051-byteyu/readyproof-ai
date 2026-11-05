"""③ 診断結果の第3階層：要件の詳細を4つの面に分けて、選んだ面だけを表示する。

  診断と対応 ／ 根拠資料 ／ 確認・質問履歴 ／ 対応・依頼

- 面の切り替えは画面の移動と同じ扱い（デモでも使える）。中の確定・保存などはデモでは押せない（readonly.scope）
- 面の切り替えに st.segmented_control を使う。件数が変わっても選択が保たれ、選んだ面だけを描画するため
- 引用原文は書き換えず、そのまま表示する（AIの理由とは見た目を分ける）
"""
from __future__ import annotations

import streamlit as st

from ...core import ACTION_TYPES, DIAG_CATEGORIES
from ...logic import rules
from ...logic.stale import diagnosis_stale_reasons
from .. import evidence_picker, readonly, state
from ..components import evidence_view, name_required, validity_note
from ..theme import box, category_chip, chip, esc, review_chip, section
from . import diagnosis, questions

NL = chr(10)
TABS = {"main": "診断と対応", "evidence": "根拠資料", "log": "確認・質問履歴", "act": "対応・依頼"}


def render(p, r, dg):
    st.markdown(f"<div class='rp-reqtext'><span class='lb'>自社の要件（第{r['version']}版）</span>{esc(r['rules'] or r['workflow'])}</div>",
                unsafe_allow_html=True)
    if r.get("open_issues"):
        st.markdown(f"<div class='rp-small'>未確定の点：{esc(r['open_issues'])}</div>", unsafe_allow_html=True)
    if not dg:
        _no_diagnosis(p, r)
        return
    nq = len([q for q in p["questions"] if r["id"] in q.get("req_ids", [])])
    label = {"main": TABS["main"], "evidence": f"{TABS['evidence']}（{len(dg['evidence'])}）", "log": f"{TABS['log']}（{nq}）",
             "act": TABS["act"]}
    key = f"dtab_{r['id']}"
    if st.session_state.get(key) not in TABS:
        st.session_state[key] = "main"
    tab = st.segmented_control("詳細の表示", list(TABS), format_func=lambda k: label[k], key=key, label_visibility="collapsed",
                               width="stretch")
    with readonly.scope(state.is_demo()):  # デモは見るだけ（確認・作成・採用などは押せない）
        {"main": _main, "evidence": _evidence, "log": _log, "act": _act}[tab or "main"](p, r, dg)


def _no_diagnosis(p, r):
    if r["status"] != "確定":
        st.info("要件が未確定のため、診断していません。② 自社のルールで確定すると、診断できるようになります。")
        if st.button("② 自社のルールへ", key=f"to_rule_{r['id']}", icon=":material/arrow_forward:"):
            state.goto("input2")
    else:
        st.info("まだ診断していません。画面上部の「AIで診断する」で診断してください。")


def _conditions(dg):
    def col(title, items):
        li = "".join(f"<li>{esc(x)}</li>" for x in items) or "<li>なし</li>"
        return f"<div><div class='h'>{esc(title)}</div><ul>{li}</ul></div>"

    # 3列の間に薄い縦線を入れて読みやすくする（CSS：.rp-cond3）
    st.markdown("<div class='rp-cond3'>" + col("満たす条件", dg["met_conditions"])
                + col("残る条件（ベンダー確認が必要）", dg["remaining_conditions"])
                + col("実機テストで確認すること", dg.get("test_conditions", [])) + "</div>", unsafe_allow_html=True)


def _main(p, r, dg):
    """なぜその判断か、何が残っているか、次に何を確かめるか。"""
    stale = diagnosis_stale_reasons(p, dg)
    st.markdown(category_chip(dg["category"]) + review_chip(dg["review_status"], dg["origin"])
                + (chip("再確認が必要", "bad") if stale else ""))
    for s in stale:
        st.warning("再確認が必要：" + s)
    for a in dg.get("auto_adjustments", []):
        st.caption("自動調整：" + a)
    for pr in (dg.get("validation") or {}).get("problems", []):
        st.error(pr)
    st.markdown(f"<div class='rp-body'><b>理由</b>　{esc(dg['reason'])}</div>", unsafe_allow_html=True)
    _conditions(dg)
    if dg.get("plan_conditions"):
        st.markdown(chip("プラン・オプション条件", "warn") + esc(dg["plan_conditions"]), unsafe_allow_html=True)
    if dg.get("constraints"):
        st.caption("制約：" + dg["constraints"])
    st.markdown(f"<div class='rp-body'><b>次に確認すること</b>　{esc(dg.get('next_check') or '未記入')}</div>", unsafe_allow_html=True)
    st.caption(f"診断ID：{dg['id']}（要件 第{dg['req_version']}版に対する診断）")


def _evidence(p, r, dg):
    """根拠の原文。引用は書き換えず、資料名・位置と一緒に示す。"""
    pid = state.product_id()
    st.caption("原文をそのまま表示しています（印の部分が引用）。AIの要約ではありません。")
    if not dg["evidence"]:
        st.caption("根拠がありません（記載・発言がないことは「対応不可」ではありません）。")
    for i, ev in enumerate(dg["evidence"]):
        with box():
            evidence_view(p, ev, pid, i)
            if st.button("この根拠を外す", key=f"rm_ev_{dg['id']}_{i}", type="tertiary"):
                dg["evidence"].pop(i)
                dg["review_status"] = "未確認"
                rules.check_diagnosis(p, dg)
                st.rerun()
    validity_note()
    if dg.get("rejected_evidence"):
        with st.expander(f"検証で除外したAIの引用（{len(dg['rejected_evidence'])}件）"):
            for ev in dg["rejected_evidence"]:
                st.markdown(f"- 参照 {esc(ev.get('ref') or ev.get('seg_id') or ev.get('utt_id'))}：『{esc(ev.get('quote'))}』",
                            unsafe_allow_html=True)
    with st.expander("根拠を追加する"):
        ev = evidence_picker.pick(p, f"form_addev_{dg['id']}")
        if ev and st.button("根拠に追加", key=f"addev_{dg['id']}"):
            if not ev["quote"]:
                st.error("引用を入力してください。")
            else:
                dg["evidence"].append(ev)
                dg["review_status"] = "未確認"
                rules.check_diagnosis(p, dg)
                st.rerun()
    diagnosis.candidates(p, r, pid)


def _log(p, r, dg):
    """人の確認、ベンダーとのやり取り、診断の更新履歴。"""
    section("人の確認")
    st.caption("人の確認は「診断の内容を読んだ」という記録です。実機で動作を確かめたことにはなりません。")
    with box():
        c1, c2 = st.columns([2, 1])
        cat = c1.selectbox("診断区分", DIAG_CATEGORIES, index=DIAG_CATEGORIES.index(dg["category"]), key=f"form_cat_{dg['id']}")
        status = c2.radio("確認結果", ["人が確認済み", "要修正"], key=f"form_rs_{dg['id']}", horizontal=True)
        comment = st.text_input("確認コメント", key=f"form_rc_{dg['id']}", value=dg.get("review_comment", ""))
        if st.button("確認結果を記録", type="primary", key=f"rev_{dg['id']}"):
            by = name_required()
            if by:
                try:
                    rules.review_diagnosis(p, dg, by, status, comment, cat)
                    state.flash(f"{dg['id']} を「{status}」にしました。")
                    st.rerun()
                except rules.RuleError as e:
                    st.error(str(e))
        if dg.get("reviewed_by"):
            st.caption(f"前回の確認：{dg['reviewed_by']}（自己申告）{dg['reviewed_at']}")

    section("ベンダーへの質問と回答")
    qs = [q for q in p["questions"] if r["id"] in q.get("req_ids", [])]
    if not qs:
        st.caption("この要件の質問はありません。「対応・依頼」で作れます。")
    for q in qs:
        with box():
            questions.question_detail(p, q)

    olds = [d for d in p["diagnoses"] if d["req_id"] == r["id"] and d.get("superseded_by")]
    if olds:
        section("診断の更新履歴")
        st.caption("以前の診断は最新の結果に流用しません。")
        for d in olds:
            st.markdown(f"{category_chip(d['category'])}<span class='rp-small'>{esc(d['id'])} 要件第{d['req_version']}版／"
                        f"{esc(d['origin'])}／{esc(d['created_at'])}</span><div class='rp-body'>{esc(d['reason'])}</div>",
                        unsafe_allow_html=True)


def _act(p, r, dg):
    """未解決の点と、質問・対応方法・依頼書の作成。"""
    section("未解決の点")
    if dg["remaining_conditions"]:
        st.markdown(NL.join(f"- {x}" for x in dg["remaining_conditions"]))
    else:
        st.caption("ベンダー確認が必要な条件は残っていません。")
    if st.button("この要件について質問を作る", key=f"mkq_{r['id']}", icon=":material/help:"):
        rem = "、".join(dg["remaining_conditions"]) if dg["remaining_conditions"] else "設定方法・対象プラン・追加費用の有無"
        q = rules.add_question(p, {"req_ids": [r["id"]], "diag_id": dg["id"],
                                   "background": f"自社の要件「{r['business']}」：{r['rules']}",
                                   "question": f"この要件について、次の点を教えてください：{rem}",
                                   "points": NL.join(["・対応できるか", "・対象プラン・オプション", "・設定方法", "・追加費用の有無"])})
        state.flash(f"{q['id']}（下書き）を作りました。「確認・質問履歴」で内容を直して確定してください。")
        st.rerun()

    actions = [a for a in p["actions"] if a["req_id"] == r["id"]]
    if dg["category"] in DIAG_CATEGORIES[:2] and not actions:
        return
    section("合わない部分への対応と依頼書")
    for a in actions:
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
            rules.add_action(p, {"req_id": r["id"], "diag_id": dg["id"], "type": typ, "reason": reason})
            st.rerun()
    for c in [c for c in p["requests"] if r["id"] in c.get("req_ids", [])]:
        with box():
            questions.request_detail(p, c)
    if st.button("この要件の依頼書を作る（下書き）", key=f"mkcr_{r['id']}", icon=":material/edit_note:"):
        _make_request(p, r, dg)


def _make_request(p, r, dg):
    kind = "調査依頼" if dg["category"] not in DIAG_CATEGORIES[2:4] else "改修依頼"
    c = rules.add_request(p, {"title": f"{r['business']}への対応", "kind": kind, "phase": "資料診断段階の懸念",
                              "req_ids": [r["id"]], "diag_ids": [dg["id"]],
                              "background": dg["reason"], "needed_behavior": r["rules"],
                              "acceptance_criteria": r["rules"], "priority": "中"})
    state.flash(f"{c['id']}（下書き）を作りました。内容を直して確定してください。")
    st.rerun()

