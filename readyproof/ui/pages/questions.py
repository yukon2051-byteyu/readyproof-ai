"""4 質問・対応依頼（質問と回答／対応方法／依頼書）。"""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from ...ai.tasks import build_request_input, run_request_draft
from ...core import ACTION_TYPES, REQUEST_KINDS, REQUEST_PHASE, REQUEST_STATUS, find
from ...export.excel import questionnaire_workbook, request_workbook
from ...logic import rules
from ...logic.evidence import evidence_label
from .. import evidence_picker, state
from ..components import ai_panel, context_bar, evidence_view, name_required, page_title, run_ai
from ..theme import REQUEST_TONE, chip, esc, section, box

VIEWS = ["質問", "対応方法", "依頼書"]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def render():
    p = state.require_project()
    if not p:
        return
    context_bar("questions")
    page_title("4 質問・対応依頼",
               "不明点はベンダーへの質問に、合わない部分は対応方法を検討して依頼書にします。作成しただけでは送付済みになりません（自動送信はしません）。")
    if "_goto_qview" in st.session_state:
        st.session_state.q_view = st.session_state.pop("_goto_qview")
    view = st.segmented_control("表示", VIEWS, key="q_view", default=VIEWS[0], label_visibility="collapsed") or VIEWS[0]
    {"質問": questions, "対応方法": actions, "依頼書": requests}[view](p)


# ======================= 質問 =======================
def questions(p):
    qs = p["questions"]
    left, right = st.columns([2, 3], gap="medium")
    with left:
        if qs:
            df = pd.DataFrame([{"ID": q["id"], "状態": q["status"], "要件": ",".join(q["req_ids"]),
                                "質問": q["question"][:50], "作成": q["origin"]} for q in qs])
            ev = st.dataframe(df, hide_index=True, on_select="rerun", selection_mode="single-row", key="q_table",
                              width="stretch", height=min(400, 38 + 35 * len(df)))
            if ev.selection.rows:
                st.session_state.sel_q = qs[ev.selection.rows[0]]["id"]
            st.download_button("質問書をExcelで出力", questionnaire_workbook(p), file_name=f"{p['project']['id']}_質問書.xlsx",
                               mime=XLSX, icon=":material/download:")
        else:
            st.info("質問はまだありません。")
        with st.expander("質問を追加する", expanded=bool(st.session_state.get("prefill_question"))):
            pre = st.session_state.pop("prefill_question", None) or {}
            reqs = [r["id"] for r in p["requirements"] if r["status"] != "廃止"]
            with st.form("form_q_new", clear_on_submit=True):
                rs = st.multiselect("関連要件", reqs, default=[x for x in pre.get("req_ids", []) if x in reqs])
                bg = st.text_area("背景", value=pre.get("background", ""), height=70)
                qt = st.text_area("質問文", value=pre.get("question", ""), height=70,
                                  placeholder="設定方法・プラン・制限・追加費用など、判断に必要なことを具体的に")
                pts = st.text_area("回答してほしい点", value=pre.get("points", ""), height=60)
                if st.form_submit_button("下書きとして追加", type="primary"):
                    try:
                        q = rules.add_question(p, {"req_ids": rs, "diag_id": pre.get("diag_id", ""), "background": bg,
                                                   "question": qt, "points": pts})
                        st.session_state.sel_q = q["id"]
                        st.rerun()
                    except rules.RuleError as e:
                        st.error(str(e))
    with right:
        q = find(p, "questions", st.session_state.get("sel_q") or qs[0]["id"]) if qs else None
        if not q:
            st.info("左の一覧から質問を選んでください。")
            return
        question_detail(p, q)


def question_detail(p, q):
    st.markdown(f"{chip(q['status'], 'ok' if q['status'] == '回答確認済み' else ('warn' if q['status'] in ('送付済み', '回答あり') else 'muted'))}"
                f"{chip(q['origin'], 'info')}<b>{esc(q['id'])}</b> <span class='rp-small'>関連要件 {esc(', '.join(q['req_ids']) or 'なし')}</span>",
                unsafe_allow_html=True)
    if q["status"] == "下書き":
        with st.form(f"form_qe_{q['id']}"):
            bg = st.text_area("背景", value=q["background"], height=80)
            qt = st.text_area("質問文", value=q["question"], height=70)
            pts = st.text_area("回答してほしい点", value=q["points"], height=70)
            c1, c2 = st.columns(2)
            save = c1.form_submit_button("保存")
            fix = c2.form_submit_button("この内容で確定", type="primary")
        if save or fix:
            q.update({"background": bg, "question": qt, "points": pts})
            if fix:
                if not name_required():
                    return
                q["status"] = "確定"
            st.rerun()
    else:
        st.markdown(f"**背景**<div class='rp-quote'>{esc(q['background'])}</div>**質問**<div class='rp-quote'>{esc(q['question'])}</div>"
                    f"**回答してほしい点**<div class='rp-quote'>{esc(q['points'])}</div>", unsafe_allow_html=True)
    for ev in q.get("evidence", []):
        evidence_view(p, ev, state.product_id())
    if q["status"] == "確定":
        c1, c2 = st.columns(2)
        sent = c1.date_input("送付日", value=date.today(), key=f"form_sent_{q['id']}")
        if c2.button("送付したことを記録", key=f"sent_{q['id']}"):
            try:
                rules.mark_question_sent(p, q, state.user_name(), str(sent))
                st.rerun()
            except rules.RuleError as e:
                st.error(str(e))
        st.caption("このアプリはメールを送信しません。実際に送付した後で記録してください。")
    if q["status"] in ("送付済み", "確定", "回答あり"):
        with box():
            section("回答を記録する")
            src = st.radio("回答元", ["手動入力", "資料", "確認済み営業発言"], horizontal=True, key=f"form_as_{q['id']}")
            text = st.text_area("回答本文（受け取った内容をそのまま）", value=q.get("answer_text", ""), key=f"form_at_{q['id']}")
            d = st.date_input("回答日", value=date.today(), key=f"form_ad_{q['id']}")
            ev = None
            if src == "資料":
                ev = evidence_picker.pick(p, f"form_aev_{q['id']}", allow=("source",))
            elif src == "確認済み営業発言":
                ev = evidence_picker.pick(p, f"form_aev_{q['id']}", allow=("utterance",))
            if st.button("回答を記録", key=f"ans_{q['id']}"):
                try:
                    rules.record_answer(p, q, text, src, str(d), state.user_name(), [ev] if ev else [])
                    st.rerun()
                except rules.RuleError as e:
                    st.error(str(e))
    if q.get("answer_text"):
        st.markdown(f"**回答**（{esc(q['answer_source'])}・{esc(q['answer_date'])}）<div class='rp-quote'>{esc(q['answer_text'])}</div>",
                    unsafe_allow_html=True)
        for ev in q.get("answer_evidence", []):
            evidence_view(p, ev, state.product_id())
        if q["status"] == "回答あり":
            review = st.text_input("確認結果のメモ", key=f"form_ar_{q['id']}")
            if st.button("回答を確認済みにする", type="primary", key=f"arv_{q['id']}"):
                by = name_required()
                if by:
                    try:
                        rules.confirm_answer(p, q, by, review)
                        st.rerun()
                    except rules.RuleError as e:
                        st.error(str(e))
        if q["status"] == "回答確認済み":
            st.caption(f"確認者：{q['answer_reviewed_by']}（自己申告）　{q.get('answer_review', '')}")
            if q["req_ids"] and st.button("回答をもとに診断の更新候補を作る", key=f"upd_{q['id']}", icon=":material/update:"):
                for rid in q["req_ids"]:
                    cur = rules.current_diagnosis(p, rid)
                    rules.add_diagnosis(p, {
                        "req_id": rid, "product_id": state.product_id(),
                        "category": cur["category"] if cur else "情報不足・ベンダー確認が必要",
                        "reason": f"{q['id']} のベンダー回答を反映（区分は人が見直してください）。" + (cur["reason"] if cur else ""),
                        "met_conditions": cur["met_conditions"] if cur else [],
                        "remaining_conditions": cur["remaining_conditions"] if cur else [],
                        "test_conditions": cur.get("test_conditions", []) if cur else [],
                        "evidence": (cur["evidence"] if cur else []) + [{"ref_type": "answer", "question_id": q["id"],
                                                                         "quote": q["answer_text"], "kind": "ベンダー回答"}],
                        "plan_conditions": cur.get("plan_conditions", "") if cur else "",
                        "next_check": "回答内容を実機テストで確認する"}, origin="手動")
                state.focus_requirement(q["req_ids"][0])
                state.flash("診断の更新候補（未確認）を作りました。区分と根拠を確認してください。テスト合格にはなりません。")
                state.goto("diagnosis")
    if q["status"] not in ("回答確認済み", "取り下げ") and st.button("取り下げ", key=f"wd_{q['id']}"):
        q["status"] = "取り下げ"
        st.rerun()


# ======================= 対応方法 =======================
def actions(p):
    reqs = [r for r in p["requirements"] if r["status"] != "廃止"]
    if not reqs:
        st.info("要件がありません。")
        return
    ids = [r["id"] for r in reqs]
    cur = st.session_state.get("sel_action_req")
    rid = st.selectbox("要件", ids, index=ids.index(cur) if cur in ids else 0,
                       format_func=lambda i: f"{i}：{find(p, 'requirements', i)['business']}")
    st.session_state.sel_action_req = rid
    dg = rules.current_diagnosis(p, rid)
    st.caption(f"現在の診断：{dg['category'] if dg else '診断なし'}。要件との違いだけで不具合・契約違反と断定せず、"
               "合意済み仕様か追加要望かを区別してください。見送りにしても適合・合格にはなりません。")
    acts = [a for a in p["actions"] if a["req_id"] == rid]
    for a in acts:
        with box():
            tone = {"採用": "ok", "不採用": "muted", "候補": "info"}[a["status"]]
            st.markdown(f"{chip(a['status'], tone)}{chip(a['type'], 'info')}<b>{esc(a['id'])}</b> "
                        f"<span class='rp-small'>{esc(a['origin'])}</span><div>{esc(a['reason'])}</div>"
                        + (f"<div class='rp-small'>不明点：{esc(a['unknowns'])}</div>" if a["unknowns"] else "")
                        + (f"<div class='rp-small'>判断：{esc(a['decided_by'])}（自己申告）／{esc(a['decision_reason'])}</div>"
                           if a["decided_by"] else ""), unsafe_allow_html=True)
            if a["status"] == "候補":
                c1, c2, c3 = st.columns([2, 1, 1])
                why = c1.text_input("判断理由", key=f"form_ar_{a['id']}", label_visibility="collapsed", placeholder="判断理由")
                for col, stv in ((c2, "採用"), (c3, "不採用")):
                    if col.button(stv, key=f"act_{a['id']}_{stv}"):
                        try:
                            rules.decide_action(p, a, stv, state.user_name(), why)
                            st.rerun()
                        except rules.RuleError as e:
                            st.error(str(e))
    with st.expander("対応方法の候補を追加する"):
        with st.form(f"form_act_new_{rid}", clear_on_submit=True):
            typ = st.selectbox("対応方法", ACTION_TYPES)
            reason = st.text_area("内容と理由", height=60)
            unk = st.text_input("不明点・要確認（費用・工期・標準設定の可否などは想像で埋めない）")
            if st.form_submit_button("候補に追加"):
                rules.add_action(p, {"req_id": rid, "diag_id": dg["id"] if dg else "", "type": typ, "reason": reason,
                                     "unknowns": unk})
                st.rerun()
    if st.button("この要件の依頼書を作る", icon=":material/edit_note:"):
        st.session_state.prefill_request = {"req_ids": [rid], "diag_ids": [dg["id"]] if dg else []}
        st.session_state._goto_qview = "依頼書"
        st.rerun()


# ======================= 依頼書 =======================
def requests(p):
    crs = p["requests"]
    left, right = st.columns([2, 3], gap="medium")
    with left:
        if crs:
            df = pd.DataFrame([{"ID": c["id"], "版": c["version"], "状態": c["status"], "区分": c["kind"],
                                "件名": c["title"][:40]} for c in crs])
            ev = st.dataframe(df, hide_index=True, on_select="rerun", selection_mode="single-row", key="cr_table",
                              width="stretch", height=min(360, 38 + 35 * len(df)))
            if ev.selection.rows:
                st.session_state.sel_cr = crs[ev.selection.rows[0]]["id"]
        else:
            st.info("依頼書はまだありません。")
        new_request(p)
    with right:
        c = find(p, "requests", st.session_state.get("sel_cr") or crs[0]["id"]) if crs else None
        if c:
            request_detail(p, c)
        else:
            st.info("左の一覧から依頼書を選ぶか、新しく作成してください。")


def new_request(p):
    pre = st.session_state.get("prefill_request")
    with st.expander("依頼書を作る", expanded=bool(pre)):
        pre = pre or {}
        reqs = [r["id"] for r in p["requirements"] if r["status"] != "廃止"]
        failed_runs = [x["id"] for x in p["runs"] if x["result"] == "不合格"]
        with st.form("form_cr_new"):
            title = st.text_input("件名", value=pre.get("title", ""))
            c1, c2 = st.columns(2)
            kind = c1.selectbox("区分", REQUEST_KINDS, index=REQUEST_KINDS.index(pre.get("kind", "設定変更依頼")))
            phase = c2.selectbox("段階", REQUEST_PHASE, index=REQUEST_PHASE.index(pre.get("phase", REQUEST_PHASE[0])),
                                 help="資料・発言だけの懸念と、テストで実際に発生した現象を区別します。")
            rs = st.multiselect("関連要件", reqs, default=[x for x in pre.get("req_ids", []) if x in reqs])
            runs = st.multiselect("関連する実施結果（テストで発生した現象の場合）", failed_runs,
                                  default=[x for x in pre.get("run_ids", []) if x in failed_runs])
            to = st.text_input("依頼先")
            needed = st.text_area("必要な動き", value=pre.get("needed_behavior", ""), height=60)
            actual = st.text_area("実際の動き（テストで確認した現象のみ）", value=pre.get("actual_behavior", ""), height=60)
            acc = st.text_area("受入条件（1行に1つ）", height=70)
            if st.form_submit_button("下書きとして作成", type="primary"):
                test_ids = sorted({find(p, "runs", r)["test_id"] for r in runs})
                try:
                    c = rules.add_request(p, {"title": title, "kind": kind, "phase": phase, "req_ids": rs, "run_ids": runs,
                                              "test_ids": test_ids, "to": to, "needed_behavior": needed,
                                              "actual_behavior": actual, "acceptance_criteria": acc,
                                              "diag_ids": pre.get("diag_ids", []), "priority": "中"})
                    st.session_state.pop("prefill_request", None)
                    st.session_state.sel_cr = c["id"]
                    st.rerun()
                except rules.RuleError as e:
                    st.error(str(e))
        s = state.settings()
        if pre.get("req_ids"):
            rid = pre["req_ids"][0]
            prompt, _ = build_request_input(p, rid, pre.get("run_ids"))
            client = ai_panel("cr", f"{rid} の依頼書", prompt, 8000, ["要件・診断・根拠・回答・対応方法・テスト結果"])
            if client:
                run_ai(lambda: [run_request_draft(p, rid, pre.get("kind", "調査依頼"), client, s, pre.get("run_ids"),
                                                  state.ledger(), st.session_state.get("access_code", ""))],
                       "依頼書の下書きを作成しました。")


EDIT_FIELDS = [("background", "背景"), ("purpose", "目的"), ("spec_in_docs", "資料上の仕様"), ("sales_explanation", "営業説明"),
               ("actual_behavior", "実際の動き（テストで発生した現象）"), ("conditions", "発生条件"), ("repro_steps", "再現手順"),
               ("needed_behavior", "必要な動き"), ("gap", "差分"), ("impact", "業務影響"), ("scope", "希望範囲"),
               ("out_of_scope", "対象外"), ("priority_reason", "優先度の理由"), ("desired_date", "希望時期"),
               ("desired_date_reason", "希望時期の理由"), ("assumptions", "前提・未確定事項"),
               ("questions_to_vendor", "相手への質問"), ("acceptance_criteria", "受入条件"), ("test_candidates", "テスト候補")]


def request_detail(p, c):
    st.markdown(f"{chip(c['status'], REQUEST_TONE.get(c['status'], 'muted'), c['status'] == '下書き')}{chip(c['kind'], 'info')}"
                f"{chip(c['phase'], 'warn' if c['phase'] == 'テストで発生した現象' else 'muted')}<b>{esc(c['id'])} 第{c['version']}版</b> "
                f"<span class='rp-small'>{esc(c['origin'])}</span><div><b>{esc(c['title'])}</b></div>", unsafe_allow_html=True)
    st.download_button("この依頼書をExcelで出力", request_workbook(p, c["id"]), file_name=f"{c['id']}_v{c['version']}_依頼書.xlsx",
                       mime=XLSX, icon=":material/download:", key=f"dl_{c['id']}")
    with st.expander("内容を編集する" + ("（確定後の変更は版が上がります）" if c["status"] != "下書き" else ""),
                     expanded=c["status"] == "下書き"):
        with st.form(f"form_cr_{c['id']}_{c['version']}"):
            vals = {"title": st.text_input("件名", value=c["title"])}
            c1, c2 = st.columns(2)
            vals["to"] = c1.text_input("依頼先", value=c["to"])
            vals["priority"] = c2.selectbox("優先度", ["高", "中", "低"], index=["高", "中", "低"].index(c["priority"] or "中"))
            for k, lbl in EDIT_FIELDS:
                vals[k] = st.text_area(lbl, value=c.get(k, ""), height=60)
            if st.form_submit_button("保存"):
                if rules.update_request(p, c, vals, state.user_name()):
                    st.rerun()
    for ev in c.get("evidence", []):
        evidence_view(p, ev, state.product_id())
    if c.get("req_ids"):
        st.caption("関連要件：" + "、".join(c["req_ids"]) + "／関連テスト：" + ("、".join(c.get("test_ids", [])) or "なし")
                   + "／関連実施：" + ("、".join(c.get("run_ids", [])) or "なし"))

    with box():
        section("状態を記録する"); st.caption("送付・回答など外部の出来事は、人が記録したときだけ反映します")
        c1, c2 = st.columns([1, 2])
        new = c1.selectbox("次の状態", [x for x in REQUEST_STATUS if x != c["status"]], key=f"form_crs_{c['id']}")
        reason = c2.text_input("理由・メモ（見送り・残件付き完了は必須）", key=f"form_crr_{c['id']}")
        remain = st.checkbox("残件付きで完了にする", key=f"form_crw_{c['id']}") if new == "完了" else False
        if st.button("状態を記録", key=f"crs_{c['id']}", type="primary"):
            try:
                rules.change_request_status(p, c, new, state.user_name(), reason, remain)
                st.rerun()
            except rules.RuleError as e:
                st.error(str(e))
        if c["status_log"]:
            st.dataframe(pd.DataFrame(c["status_log"]).rename(columns={"at": "日時", "by": "記録者", "from": "前", "to": "後",
                                                                       "reason": "理由"}), hide_index=True)

    with st.expander("相手の回答・見積を記録する（不明な項目は空欄＝未回答。0円・0日にはしません）"):
        v = c["vendor"]
        with st.form(f"form_cv_{c['id']}"):
            ans = st.text_area("相手の回答", value=v.get("answer", ""), height=60)
            c1, c2 = st.columns(2)
            sp = c1.selectbox("設定で対応できるか", ["不明", "可能", "不可"], index=["不明", "可能", "不可"].index(v.get("settings_possible", "不明")))
            mn = c2.selectbox("改修が必要か", ["不明", "必要", "不要（設定変更）", "不要"],
                              index=["不明", "必要", "不要（設定変更）", "不要"].index(v.get("modification_needed", "不明")))
            c1, c2, c3, c4 = st.columns(4)
            cost = c1.text_input("見積費用", value="" if v["cost_amount"] is None else str(v["cost_amount"]))
            cur = c2.selectbox("通貨", ["", "円", "USD"], index=["", "円", "USD"].index(v.get("cost_currency", "")))
            eff = c3.text_input("工数", value="" if v["effort"] is None else str(v["effort"]))
            unit = c4.selectbox("単位", ["", "人日", "人月", "時間"], index=["", "人日", "人月", "時間"].index(v.get("effort_unit", "")))
            c1, c2 = st.columns(2)
            plan_d = c1.text_input("予定日", value=v.get("planned_date", ""))
            cons = c2.text_input("制約", value=v.get("constraints", ""))
            done = st.checkbox("相手から対応完了の連絡があった（人の確認とは別）", value=v.get("vendor_done", False))
            if st.form_submit_button("記録"):
                try:
                    rules.record_vendor_response(p, c, {"answer": ans, "settings_possible": sp, "modification_needed": mn,
                                                        "cost_amount": cost, "cost_currency": cur, "effort": eff,
                                                        "effort_unit": unit, "planned_date": plan_d, "constraints": cons,
                                                        "vendor_done": done}, state.user_name())
                    st.rerun()
                except rules.RuleError as e:
                    st.error(str(e))
    if c["completion"]["human_confirmed"]:
        st.success(f"人が確認して完了：{c['completion']['by']}（自己申告）{c['completion']['at']}"
                   + (f"／残件あり：{c['completion']['reason']}" if c["completion"]["with_remaining"] else ""))
    if c.get("acceptance_criteria", "").strip() and c.get("req_ids"):
        if st.button("受入条件からテスト候補を作る（AIなし・下書き）", key=f"cr2t_{c['id']}", icon=":material/playlist_add:"):
            n = 0
            for line in [x.strip("・-　 ") for x in c["acceptance_criteria"].splitlines() if x.strip()]:
                rules.add_test(p, {"req_ids": c["req_ids"][:1], "request_ids": [c["id"]], "title": line[:40],
                                   "purpose": f"{c['id']} の受入条件の確認", "viewpoint": "設定・改修箇所",
                                   "steps": "要確認（操作手順は対応内容の確定後に記入）", "expected": line,
                                   "expected_basis": f"{c['id']} 第{c['version']}版 受入条件", "importance": "高",
                                   "importance_reason": "受入条件", "expected_confirmed": False}, origin="手動")
                n += 1
            state.flash(f"{n}件のテスト候補（下書き）を作りました。既存のテストを使える場合は、そちらに関連付けてください。")
            st.session_state.test_filter_req = c["req_ids"][0]
            state.goto("tests")
    st.caption("根拠一覧：" + " / ".join(evidence_label(p, ev, with_quote=False) for ev in c.get("evidence", [])) if c.get("evidence") else "")
