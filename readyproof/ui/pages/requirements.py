"""② 自社のルール（要件）の部品：質問形式・AIの聞き取り・文章からの分割・手入力・詳細と確定。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ...ai.tasks import run_split, split_prompt
from ...core import REQ_PRIORITY, find, primary_product
from ...intake import TEMPLATES, UNKNOWN, build_requirements, suggest_template, transcript, visible_questions
from ...logic import rules
from .. import state
from ..components import ai_panel, context_bar, name_required, page_title, run_ai
from ..theme import box, chip, esc

LABELS = {"business": "業務名", "workflow": "作業内容・流れ", "role": "操作する役割", "rules": "ルール・条件・例外の扱い",
          "exceptions": "例外", "inputs": "入力", "outputs": "出力", "priority": "重要度", "reason": "理由",
          "basis": "自社資料・発言の根拠", "open_issues": "未確定事項（曖昧・矛盾）", "original_text": "元の文章"}


def render():
    p = state.require_project()
    if not p:
        return
    context_bar("requirements")
    page_title("2 自社の仕事・ルール",
               "自社の業務ルール・作業手順・必須条件を要件にします。製品の仕様とは分けて管理し、人が確定します。")
    left, right = st.columns([2, 3], gap="medium")
    with left:
        req_list(p)
    with right:
        tabs = ["質問に答えて作る", "詳細・編集", "手動で追加", "文章から分割（AI）"]
        if "_goto_req_tab" in st.session_state:
            st.session_state.req_tab = st.session_state.pop("_goto_req_tab")
        tab = st.segmented_control("操作", tabs, key="req_tab", default=tabs[1] if p["requirements"] else tabs[0],
                                   label_visibility="collapsed") or tabs[1]
        if tab == "質問に答えて作る":
            intake_view(p)
        elif tab == "詳細・編集":
            detail(p)
        elif tab == "手動で追加":
            add_manual(p)
        else:
            ai_split(p)


def req_list(p):
    reqs = p["requirements"]
    if not reqs:
        st.info("要件がありません。右の「手動で追加」または「文章から分割」で登録してください。")
        return
    df = pd.DataFrame([{"ID": r["id"], "版": r["version"], "状態": r["status"], "重要度": r["priority"],
                        "業務名": r["business"], "ルール・条件": r["rules"][:60],
                        "注意": "要確認あり" if (r.get("term_warnings") or r.get("open_issues")) else ""} for r in reqs])
    ev = st.dataframe(df, hide_index=True, on_select="rerun", selection_mode="single-row", key="req_table",
                      width="stretch", height=min(420, 38 + 35 * len(df)))
    rows = ev.selection.rows if ev and ev.selection else []
    if rows:
        st.session_state.sel_req = reqs[rows[0]]["id"]
    st.caption(f"{len(reqs)}件（確定 {sum(1 for r in reqs if r['status'] == '確定')}件・下書き "
               f"{sum(1 for r in reqs if r['status'] == '下書き')}件・廃止 {sum(1 for r in reqs if r['status'] == '廃止')}件）")


def _fields_form(prefix: str, r: dict | None) -> dict:
    r = r or {}
    out = {}
    c1, c2 = st.columns([2, 1])
    out["business"] = c1.text_input(LABELS["business"], value=r.get("business", ""), key=f"{prefix}_business")
    pr = r.get("priority") or "必須"
    out["priority"] = c2.selectbox(LABELS["priority"], REQ_PRIORITY, index=REQ_PRIORITY.index(pr), key=f"{prefix}_priority")
    out["workflow"] = st.text_area(LABELS["workflow"], value=r.get("workflow", ""), height=60, key=f"{prefix}_workflow")
    c1, c2 = st.columns(2)
    out["role"] = c1.text_input(LABELS["role"], value=r.get("role", ""), key=f"{prefix}_role")
    out["reason"] = c2.text_input(LABELS["reason"], value=r.get("reason", ""), key=f"{prefix}_reason")
    out["rules"] = st.text_area("ルール・条件（金額・以上／未満・禁止を正確に）", value=r.get("rules", ""), height=80,
                                key=f"{prefix}_rules")
    out["exceptions"] = st.text_area(LABELS["exceptions"], value=r.get("exceptions", ""), height=50, key=f"{prefix}_exceptions")
    c1, c2 = st.columns(2)
    out["inputs"] = c1.text_input(LABELS["inputs"], value=r.get("inputs", ""), key=f"{prefix}_inputs")
    out["outputs"] = c2.text_input(LABELS["outputs"], value=r.get("outputs", ""), key=f"{prefix}_outputs")
    out["basis"] = st.text_input(LABELS["basis"], value=r.get("basis", ""), key=f"{prefix}_basis",
                                 placeholder="例：経費精算規程 第3条（DOC-002）")
    out["open_issues"] = st.text_area(LABELS["open_issues"], value=r.get("open_issues", ""), height=50,
                                      key=f"{prefix}_open")
    out["original_text"] = st.text_area(LABELS["original_text"], value=r.get("original_text", ""), height=60,
                                        key=f"{prefix}_orig", help="元の規程・手順書の文章。分割時に数値や条件が落ちていないかの確認に使います。")
    return out


def detail(p):
    rid = st.session_state.get("sel_req") or (p["requirements"][0]["id"] if p["requirements"] else None)
    r = find(p, "requirements", rid) if rid else None
    if not r:
        st.info("左の一覧から要件を選んでください。")
        return
    st.markdown(f"{chip(r['status'], 'ok' if r['status'] == '確定' else 'muted', draft=r['status'] == '下書き')}"
                f"{chip(r['origin'], 'info')}<b>{esc(r['id'])} 第{r['version']}版</b> "
                f"<span class='rp-small'>{esc('確定者：' + r['confirmed_by'] if r.get('confirmed_by') else '')}</span>",
                unsafe_allow_html=True)
    for w in r.get("term_warnings", []):
        st.warning(f"元の文章にある「{w}」が、分割後の項目に見当たりません。落ちていないか確認してください。")
    if r.get("open_issues"):
        st.warning("未確定事項：" + r["open_issues"])
    if r["status"] == "確定":
        st.caption("確定済みの要件を変更すると版が上がり、関連する診断・テストは「再確認が必要」になります。")
    with st.form(f"form_req_{r['id']}_{r['version']}"):
        vals = _fields_form(f"ed_req_{r['id']}_{r['version']}", r)
        reason = st.text_input("変更理由（確定後の変更時）", key=f"ed_req_reason_{r['id']}")
        saved = st.form_submit_button("変更を保存", disabled=r["status"] == "廃止")
    if saved:
        if rules.update_requirement(p, r, vals, state.user_name(), reason):
            state.flash(f"{r['id']} を更新しました（第{r['version']}版）。")
            st.rerun()
        else:
            st.info("変更はありません。")
    c1, c2, c3 = st.columns(3)
    if c1.button("この内容で確定", type="primary", disabled=r["status"] != "下書き", key=f"conf_{r['id']}"):
        by = name_required()
        if by:
            try:
                rules.confirm_requirement(p, r, by)
                state.flash(f"{r['id']} を確定しました。")
                st.rerun()
            except rules.RuleError as e:
                st.error(str(e))
    with c2.popover("廃止する", disabled=r["status"] == "廃止"):
        why = st.text_input("廃止の理由", key=f"form_retire_{r['id']}")
        if st.button("廃止", key=f"retire_{r['id']}"):
            by = name_required()
            if by:
                try:
                    rules.retire_requirement(p, r, by, why)
                    st.rerun()
                except rules.RuleError as e:
                    st.error(str(e))
    if c3.button("この要件の診断へ", key=f"to_diag_{r['id']}", icon=":material/arrow_forward:"):
        state.focus_requirement(r["id"])
        state.goto("diagnosis")
    if r.get("history"):
        with st.expander(f"版の履歴（{len(r['history'])}件）"):
            for h in reversed(r["history"]):
                st.markdown(f"**第{h['version']}版**（{esc(h['at'])}・{esc(h['by'] or '名前なし')}・{esc(h['reason'])}）")
                st.caption(f"ルール：{h['data'].get('rules', '')}")


def add_manual(p):
    with st.form("form_req_new", clear_on_submit=True):
        vals = _fields_form("form_req_new", None)
        ok = st.form_submit_button("下書きとして追加", type="primary")
    if ok:
        if not (vals["business"].strip() and (vals["rules"].strip() or vals["workflow"].strip())):
            st.error("業務名と、作業内容またはルール・条件を入力してください。")
            return
        r = rules.add_requirement(p, vals, origin="手動", by=state.user_name())
        st.session_state.sel_req = r["id"]
        state.flash(f"{r['id']} を下書きとして追加しました。内容を確認して確定してください。")
        st.rerun()


def ai_split(p):
    st.caption("社内規程や手順書の文章から、要件の分割候補を作ります。結果は下書きで、人が確定します。")
    own = [s for s in p["sources"] if s["owner"] == "自社"]
    src_opt = ["（貼り付け）"] + [f"{s['id']}：{s['name']}" for s in own]
    choice = st.selectbox("元の文章", src_opt)
    if choice == "（貼り付け）":
        text = st.text_area("自社の業務ルール・作業手順", height=180, key="form_split_text")
    else:
        s = next(x for x in own if x["id"] == choice.split("：")[0])
        text = "\n".join(g["text"] for g in s["segments"] if g.get("selected"))
        st.text_area("送る文章（分析対象に選んだ箇所のみ）", value=text, height=180, disabled=True)
    if not text.strip():
        return
    client = ai_panel("split", "要件の分割", split_prompt(text), 8000, ["自社の文章"])
    if client:
        s = state.settings()
        run_ai(lambda: run_split(p, text, client, s, state.ledger(), st.session_state.get("access_code", "")),
               "{n}件の要件候補（下書き）を作成しました。")


# ---------------- 質問に答えて作る（AIなし） ----------------
def intake_view(p):
    st.caption("業務の種類ごとの質問に答えると、要件の下書きを作ります。分からない点は「分からない・未定」を選べば、"
               "推測で埋めずに未確定事項として残します（料金なし・AI不使用）。")
    prod = primary_product(p) or {}
    pj = p["project"]
    guess = suggest_template(pj.get("name", ""), pj.get("target_business", ""), prod.get("name", ""))
    ids = list(TEMPLATES.keys())
    tid = st.selectbox("業務の種類", ids, index=ids.index(st.session_state.get("intake_tid", guess)),
                       format_func=lambda t: TEMPLATES[t]["label"] + ("（おすすめ）" if t == guess else ""))
    if st.session_state.get("intake_tid") != tid:
        st.session_state.intake_tid, st.session_state.intake_i = tid, 0
        st.session_state.intake_ans = {}
    ans = st.session_state.setdefault("intake_ans", {})
    qs = visible_questions(tid, ans)
    i = min(st.session_state.get("intake_i", 0), len(qs))
    if i < len(qs):
        q = qs[i]
        with box():
            st.progress((i) / len(qs), text=f"質問 {i + 1} / {len(qs)}")
            st.markdown(f"**{q['q']}**")
            if q.get("help"):
                st.caption(q["help"])
            key = f"intake_{tid}_{q['id']}"
            cur = ans.get(q["id"], q.get("default", ""))
            if q["type"] == "choice":
                opts = q["options"]
                val = st.radio("回答", opts, index=opts.index(cur) if cur in opts else None, key=key,
                               label_visibility="collapsed")
            elif q["type"] == "number":
                unk = st.checkbox(UNKNOWN, value=cur == UNKNOWN, key=key + "_unk")
                val = UNKNOWN if unk else st.number_input("回答", min_value=0.0, step=1.0, key=key,
                                                         value=float(cur) if isinstance(cur, (int, float)) else None,
                                                         label_visibility="collapsed", placeholder="数字を入力")
            else:
                val = st.text_input("回答", value=cur or "", key=key, label_visibility="collapsed")
            c1, c2, _ = st.columns([1, 1, 3])
            if c1.button("戻る", disabled=i == 0, key=f"intake_back_{i}", width="stretch"):
                st.session_state.intake_i = i - 1
                st.rerun()
            if c2.button("次へ", type="primary", key=f"intake_next_{i}", width="stretch",
                         disabled=(q["type"] == "choice" and val is None) or (q["type"] == "number" and val is None)):
                ans[q["id"]] = val
                st.session_state.intake_i = i + 1
                st.rerun()
        return

    drafts = build_requirements(tid, ans)
    with box():
        st.progress(1.0, text="すべての質問に回答しました")
        st.markdown(f"**要件の下書き：{len(drafts)}件**（登録後、内容を確認して確定してください）")
        for d in drafts:
            st.markdown(f"- **{esc(d['business'])}**（{esc(d['priority'])}）：{esc(d['rules'])}"
                        + (f"　:orange[未確定：{esc(d['open_issues'])}]" if d.get("open_issues") else ""))
        if st.toggle("回答の原文を見る（要件の「元の文章」に残ります）", key="intake_show_src"):
            st.text(transcript(tid, ans))
        c1, c2, _ = st.columns([1.4, 1, 2])
        if c1.button("登録", type="primary", disabled=not drafts, width="stretch"):
            made = [rules.add_requirement(p, d, origin="質問形式", by=state.user_name()) for d in drafts]
            st.session_state.sel_req = made[0]["id"]
            st.session_state.intake_ans, st.session_state.intake_i = {}, 0
            st.session_state._goto_req_tab = "詳細・編集"
            state.flash(f"{len(made)}件の要件を登録しました。内容を確認して確定してください。")
            st.rerun()
        if c2.button("最初からやり直す", width="stretch"):
            st.session_state.intake_ans, st.session_state.intake_i = {}, 0
            st.rerun()


# ---------------- AIの聞き取り（BL-001 案B） ----------------
def ai_interview_view(p):
    """AIが製品資料を踏まえて質問を作り、回答から要件の下書きを作る。質問・回答は画面を閉じるまでの一時的なもの。"""
    from ...ai.tasks import (UNKNOWN_ANSWER, build_interview_input, interview_split_prompt, interview_transcript,
                             run_interview, run_interview_split)

    st.caption("AIが、読み込んだ製品の資料を踏まえて「この製品が合うか確かめるために、自社について聞くべきこと」を質問します。"
               "答えると、AIが要件の下書きにまとめます（AIを2回使います・料金あり）。分からない点は「分からない・未定」で大丈夫です。")
    iv = st.session_state.setdefault("aiq", {"questions": [], "answers": {}, "i": 0})
    s = state.settings()
    code = st.session_state.get("access_code", "")

    # 1. 質問を作る
    if not iv["questions"]:
        business = st.text_input("聞き取る業務", value=p["project"].get("target_business", ""),
                                 placeholder="例：経費の申請・承認", key="aiq_business")
        if not business.strip():
            return
        prompt = build_interview_input(p, business.strip(), state.product_id())
        client = ai_panel("interview", "聞き取りの質問づくり", prompt, 4000, ["案件の情報", "製品資料の抜粋（分析の対象に選んだ箇所）"],
                          button_label="AIに質問を作ってもらう")
        if client:
            def make():
                iv["questions"] = run_interview(p, business.strip(), state.product_id(), client, s, state.ledger(), code)
                iv["answers"], iv["i"] = {}, 0
                return iv["questions"]
            run_ai(make, "{n}問の質問を作りました。順番に答えてください。")
        return

    qs, ans = iv["questions"], iv["answers"]
    i = min(iv["i"], len(qs))
    # 2. 1問ずつ答える
    if i < len(qs):
        q = qs[i]
        with box():
            st.progress(i / len(qs), text=f"質問 {i + 1} / {len(qs)}" + (f"（{q['topic']}）" if q.get("topic") else ""))
            st.markdown(f"**{esc(q['question'])}**", unsafe_allow_html=True)
            if q.get("why"):
                st.caption("なぜ聞くか：" + q["why"])
            key = f"aiq_{i}"
            cur = ans.get(i)
            if q["answer_type"] == "choice":
                opts = q["options"] + [UNKNOWN_ANSWER]
                val = st.radio("回答", opts, index=opts.index(cur) if cur in opts else None, key=key,
                               label_visibility="collapsed")
            else:
                unk = st.checkbox(UNKNOWN_ANSWER, value=cur == UNKNOWN_ANSWER, key=key + "_unk")
                if unk:
                    val = UNKNOWN_ANSWER
                elif q["answer_type"] == "number":
                    unit = q.get("unit", "")
                    num = st.number_input(f"回答（単位：{unit}）" if unit else "回答", min_value=0.0, step=1.0, key=key,
                                          value=float(cur) if isinstance(cur, (int, float)) else None, placeholder="数字を入力")
                    val = None if num is None else (int(num) if float(num).is_integer() else num)
                else:
                    val = st.text_input("回答", value=cur if isinstance(cur, str) and cur != UNKNOWN_ANSWER else "",
                                        key=key, label_visibility="collapsed")
            c1, c2, _ = st.columns([1, 1, 3])
            if c1.button("戻る", disabled=i == 0, key=f"aiq_back_{i}", width="stretch"):
                iv["i"] = i - 1
                st.rerun()
            if c2.button("次へ", type="primary", key=f"aiq_next_{i}", width="stretch",
                         disabled=val is None or str(val).strip() == ""):
                ans[i] = val
                iv["i"] = i + 1
                st.rerun()
        return

    # 3. 回答から要件の下書きを作る
    transcript = interview_transcript(qs, ans)
    with box():
        st.progress(1.0, text="すべての質問に回答しました")
        for n, q in enumerate(qs):
            a = ans.get(n, "")
            unit = q.get("unit", "") if q.get("answer_type") == "number" and a != UNKNOWN_ANSWER else ""
            st.markdown(f"- {esc(q['question'])}　→　**{esc(a)}{esc(unit)}**", unsafe_allow_html=True)
        client = ai_panel("interview_split", "回答から要件の下書きを作る", interview_split_prompt(transcript), 8000,
                          ["聞き取りの記録（質問と回答）"], button_label="AIで要件の下書きにする")
        if client:
            def make():
                made = run_interview_split(p, transcript, client, s, state.ledger(), code)
                st.session_state.aiq = {"questions": [], "answers": {}, "i": 0}
                return made
            run_ai(make, "{n}件の要件の下書きを作りました。内容を確認して確定してください。")
        if st.button("質問を作り直す", key="aiq_reset"):
            st.session_state.aiq = {"questions": [], "answers": {}, "i": 0}
            st.rerun()
