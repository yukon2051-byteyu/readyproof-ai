"""5 試すこと・実施結果（受入テストと実施記録）。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ...ai.tasks import build_test_input, run_tests
from ...core import RUN_RESULT, RUN_STATUS, TEST_IMPORTANCE, TEST_VIEWPOINTS, find, now_iso
from ...logic import rules
from ...logic.stale import run_stale_reasons, test_stale_reasons
from .. import state
from ..components import ai_panel, context_bar, name_required, page_title, run_ai
from ..theme import RESULT_TONE, chip, esc

FIELDS = [("purpose", "目的"), ("role", "操作する役割"), ("preconditions", "事前条件"), ("inputs", "入力"),
          ("steps", "操作手順（画面・ボタンが不明なら「要確認」）"), ("expected", "期待結果"), ("expected_basis", "期待結果の根拠"),
          ("importance_reason", "重要度の理由"), ("open_issues", "未確定事項")]


def render():
    p = state.require_project()
    if not p:
        return
    context_bar("tests")
    page_title("5 試すこと・実施結果",
               "テストを人が確定し、実際の対象システムで試した結果を記録します。資料や営業説明で「できる」とされても、ここで合格するまでは実機未確認です。")
    reqs = [r for r in p["requirements"] if r["status"] != "廃止"]
    req_ids = ["すべて"] + [r["id"] for r in reqs]
    cur = st.session_state.get("test_filter_req", "すべて")
    filt = st.selectbox("要件で絞り込む", req_ids, index=req_ids.index(cur) if cur in req_ids else 0)
    st.session_state.test_filter_req = filt
    tests = [t for t in p["tests"] if filt == "すべて" or filt in t["req_ids"]]
    left, right = st.columns([2, 3], gap="medium")
    with left:
        test_table(p, tests)
        add_test(p, reqs, filt)
    with right:
        t = find(p, "tests", st.session_state.get("sel_test", ""))
        if (not t or t not in tests) and tests:
            t = tests[0]
        if t:
            detail(p, t)
        else:
            st.info("左の一覧からテストを選んでください。")
    st.divider()
    ai_gen(p, reqs, filt)


def test_table(p, tests):
    if not tests:
        st.info("テストがありません。")
        return
    rows = []
    for t in tests:
        lr = rules.latest_run(p, t["id"])
        state_ = (lr["result"] if lr and lr["status"] == "完了" else (lr["status"] if lr else "未実施"))
        stale = bool(test_stale_reasons(p, t) or (lr and run_stale_reasons(p, lr)))
        rows.append({"ID": t["id"], "最新の結果": state_, "状態": t["status"], "再確認": "要" if stale else "",
                     "名称": t["title"][:36], "要件": ",".join(t["req_ids"]), "観点": t["viewpoint"], "版": t["version"]})
    ev = st.dataframe(pd.DataFrame(rows), hide_index=True, on_select="rerun", selection_mode="single-row",
                      key="test_table", width="stretch", height=min(440, 38 + 35 * len(rows)))
    if ev.selection.rows:
        st.session_state.sel_test = tests[ev.selection.rows[0]]["id"]


def add_test(p, reqs, filt):
    with st.expander("テストを手動で追加する"):
        with st.form("form_test_new", clear_on_submit=True):
            rs = st.multiselect("要件", [r["id"] for r in reqs], default=[filt] if filt != "すべて" else [])
            title = st.text_input("名称")
            c1, c2 = st.columns(2)
            vp = c1.selectbox("観点", TEST_VIEWPOINTS)
            imp = c2.selectbox("重要度", TEST_IMPORTANCE)
            vals = {k: st.text_area(lbl, height=50) for k, lbl in FIELDS[:7]}
            if st.form_submit_button("下書きとして追加", type="primary"):
                if not rs or not title.strip():
                    st.error("要件と名称を入力してください。")
                else:
                    t = rules.add_test(p, {"req_ids": rs, "title": title, "viewpoint": vp, "importance": imp, **vals})
                    st.session_state.sel_test = t["id"]
                    st.rerun()


def detail(p, t):
    lr = rules.latest_run(p, t["id"])
    st.markdown(f"{chip(t['status'], 'ok' if t['status'] == '確定' else 'muted', t['status'] == '下書き')}"
                f"{chip('期待結果：確定' if t.get('expected_confirmed') else '期待結果：未確定', 'ok' if t.get('expected_confirmed') else 'warn')}"
                f"{chip(t['origin'], 'info')}<b>{esc(t['id'])} 第{t['version']}版 {esc(t['title'])}</b>", unsafe_allow_html=True)
    st.caption(f"要件：{', '.join(f'{k} 第{v}版' for k, v in t.get('req_versions', {}).items())}　観点：{t['viewpoint']}　"
               f"重要度：{t['importance']}" + (f"　関連依頼：{', '.join(t['request_ids'])}" if t.get("request_ids") else ""))
    for s in test_stale_reasons(p, t):
        st.warning("再確認が必要：" + s)
    with st.expander("内容（編集すると、確定済みの場合は版が上がります）", expanded=t["status"] == "下書き"):
        with st.form(f"form_t_{t['id']}_{t['version']}"):
            vals = {"title": st.text_input("名称", value=t["title"])}
            c1, c2 = st.columns(2)
            vals["viewpoint"] = c1.selectbox("観点", TEST_VIEWPOINTS, index=TEST_VIEWPOINTS.index(t["viewpoint"])
                                             if t["viewpoint"] in TEST_VIEWPOINTS else 0)
            vals["importance"] = c2.selectbox("重要度", TEST_IMPORTANCE, index=TEST_IMPORTANCE.index(t["importance"])
                                              if t["importance"] in TEST_IMPORTANCE else 1)
            for k, lbl in FIELDS:
                vals[k] = st.text_area(lbl, value=t.get(k, ""), height=55)
            if st.form_submit_button("保存"):
                if rules.update_test(p, t, vals, state.user_name()):
                    st.rerun()
    if t["status"] == "下書き":
        c1, c2 = st.columns([2, 1])
        exp_ok = c1.checkbox("期待結果を人が確認した（未確定事項・「要確認」がない）", value=t.get("expected_confirmed", False),
                             key=f"form_expok_{t['id']}_{t['version']}")
        if c2.button("テストを確定", type="primary", key=f"tconf_{t['id']}"):
            by = name_required()
            if by:
                t["expected_confirmed"] = exp_ok
                try:
                    rules.confirm_test(p, t, by)
                    st.rerun()
                except rules.RuleError as e:
                    st.error(str(e))
    if t["status"] != "廃止" and st.button("廃止する", key=f"tret_{t['id']}"):
        t["status"] = "廃止"
        st.rerun()

    st.markdown("**実施結果を記録する**（人が実際の対象システムで試した結果）")
    with st.form(f"form_run_{t['id']}_{t['version']}", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        status = c1.selectbox("実施状態", RUN_STATUS, index=2)
        result = c2.selectbox("合否", RUN_RESULT)
        when = c3.text_input("実施日時", value=now_iso()[:16].replace("T", " "))
        c1, c2, c3 = st.columns(3)
        prod = (p["products"] or [{}])[0]
        pv = c1.text_input("製品の版", value=prod.get("edition", ""))
        plan = c2.text_input("プラン", value=prod.get("plan", ""))
        env = c3.text_input("環境", placeholder="例：検証テナント")
        actual = st.text_area("実際の結果（何が起きたか）", height=70)
        memo = st.text_input("証拠メモ（画面キャプチャの保存場所など）")
        defect = st.text_input("不具合（あれば）")
        opens = st.text_input("確認事項（実施不能の理由など）")
        if st.form_submit_button("記録する", type="primary"):
            try:
                rules.record_run(p, t, {"tester": state.user_name(), "status": status, "result": result, "actual": actual,
                                        "executed_at": when, "product_version": pv, "plan": plan, "environment": env,
                                        "evidence_memo": memo, "defect": defect, "open_points": opens})
                st.rerun()
            except rules.RuleError as e:
                st.error(str(e))
    st.caption("未確定の期待結果では「合格」を記録できません。実施不能は合否に数えません。再テストは新しい履歴として追加され、過去の結果は書き換えません。")

    runs = rules.runs_for(p, t["id"])
    if runs:
        st.markdown("**実施の履歴**")
        for r in reversed(runs):
            stale = run_stale_reasons(p, r)
            label = r["result"] if r["status"] == "完了" else r["status"]
            st.markdown(f"{chip(label, RESULT_TONE.get(label, 'muted'))}{chip('再テスト' if r['is_retest'] else '初回', 'muted')}"
                        + (chip("旧版のテストに対する結果", "bad") if stale else "")
                        + f"<b>{esc(r['id'])}</b> <span class='rp-small'>テスト第{r['test_version']}版／{esc(r['executed_at'])}／"
                          f"{esc(r['tester'])}（自己申告）／{esc(r['plan'])} {esc(r['product_version'])} {esc(r['environment'])}</span>"
                        + (f"<div class='rp-quote'>{esc(r['actual'])}</div>" if r["actual"] else "")
                        + (f"<div class='rp-small'>不具合：{esc(r['defect'])}</div>" if r["defect"] else "")
                        + (f"<div class='rp-small'>確認事項：{esc(r['open_points'])}</div>" if r["open_points"] else ""),
                        unsafe_allow_html=True)
        if lr and lr["result"] == "不合格":
            if st.button("この不合格から依頼書を作る", icon=":material/edit_note:", key=f"t2cr_{t['id']}"):
                st.session_state.prefill_request = {
                    "title": f"{t['title']}（不合格）", "kind": "不具合修正依頼", "phase": "テストで発生した現象",
                    "req_ids": t["req_ids"], "run_ids": [lr["id"]], "actual_behavior": lr["actual"],
                    "needed_behavior": t["expected"]}
                st.session_state._goto_qview = "依頼書"
                state.goto("questions")
            st.caption("要件との違いがあっても、合意済みの仕様か追加要望かを確認してから区分を選んでください（不具合と断定しない）。")


def ai_gen(p, reqs, filt):
    s = state.settings()
    st.markdown("**AIでテストの下書きを作る**")
    confirmed = [r["id"] for r in reqs if r["status"] == "確定"]
    if filt == "すべて" or filt not in confirmed:
        st.caption("上の「要件で絞り込む」で確定済みの要件を1つ選ぶと使えます。")
        return
    crs = [c["id"] for c in p["requests"] if filt in c["req_ids"] and c["status"] != "下書き"]
    cr = st.selectbox("受入条件を使う依頼書（任意・確定済みのみ）", ["なし"] + crs)
    cr = None if cr == "なし" else cr
    prompt = build_test_input(p, filt, cr)
    client = ai_panel("tests", f"{filt} のテスト（最大{s.limits.max_tests_per_generation}件）", prompt, 12000,
                      ["要件・診断の要点・受入条件"])
    if client:
        run_ai(lambda: run_tests(p, filt, client, s, cr, state.ledger(), st.session_state.get("access_code", "")),
               "{n}件のテスト（下書き）を作成しました。既存のテストは上書きしていません。")
