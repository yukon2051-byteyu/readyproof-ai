"""3 自社に合うかを確認（適合性診断）。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ...ai.tasks import build_diagnosis_input, keyword_candidates_report, run_diagnosis
from ...core import DIAG_CATEGORIES, DIAG_SHORT, find
from ...logic import rules
from ...logic.stale import diagnosis_stale_reasons
from ...media.subtitles import fmt_ts
from .. import evidence_picker, state
from ..components import (ai_panel, context_bar, evidence_view, name_required, page_title, run_ai, validity_note)
from ..theme import category_chip, chip, esc, review_chip, section, box


def render():
    p = state.require_project()
    if not p:
        return
    context_bar("diagnosis")
    page_title("3 自社に合うかを確認",
               "要件ごとに、製品の資料・営業説明を根拠として照合します。ここで分かるのは「資料・説明上の見込み」で、実機で動くかはテストで確認します。")
    reqs = [r for r in p["requirements"] if r["status"] != "廃止"]
    if not reqs:
        st.info("要件がありません。「2 自社の仕事・ルール」で登録してください。")
        if st.button("要件の登録へ"):
            state.goto("requirements")
        return
    summary(p, reqs)
    left, right = st.columns([2, 3], gap="medium")
    with left:
        rid = req_table(p, reqs)
    with right:
        if rid:
            detail(p, find(p, "requirements", rid))
    st.divider()
    ai_section(p, reqs)


def summary(p, reqs):
    counts = {c: 0 for c in DIAG_CATEGORIES}
    none, reviewed, stale = 0, 0, 0
    for r in reqs:
        dg = rules.current_diagnosis(p, r["id"])
        if not dg:
            none += 1
            continue
        counts[dg["category"]] += 1
        reviewed += dg["review_status"] == "人が確認済み"
        stale += bool(diagnosis_stale_reasons(p, dg))
    parts = [category_chip(c) + f"<b>{n}</b>" for c, n in counts.items()]
    parts.append(chip("診断なし", "muted") + f"<b>{none}</b>")
    st.markdown("　".join(parts), unsafe_allow_html=True)
    diag_n = len(reqs) - none
    st.caption(f"人が確認済み {reviewed}/{diag_n}（診断済みの要件が分母）　再確認が必要 {stale}件　"
               "※根拠のない総合点数は出していません。")


def req_table(p, reqs) -> str | None:
    rows = []
    for r in reqs:
        dg = rules.current_diagnosis(p, r["id"])
        rows.append({"要件": r["id"], "診断": DIAG_SHORT.get(dg["category"], dg["category"]) if dg else "診断なし",
                     "確認": ("済" if dg["review_status"] == "人が確認済み" else "未") if dg else "",
                     "再確認": "要" if dg and diagnosis_stale_reasons(p, dg) else "", "重要度": r["priority"],
                     "業務名": r["business"]})
    ev = st.dataframe(pd.DataFrame(rows), hide_index=True, on_select="rerun", selection_mode="single-row",
                      key="diag_table", width="stretch", height=min(460, 38 + 35 * len(rows)))
    sel = ev.selection.rows if ev and ev.selection else []
    if sel:
        st.session_state.sel_diag_req = reqs[sel[0]]["id"]
    rid = st.session_state.get("sel_diag_req")
    if rid not in [r["id"] for r in reqs]:
        rid = reqs[0]["id"]
        st.session_state.sel_diag_req = rid
    return rid


def detail(p, r):
    pid = state.product_id()
    st.markdown(f"<b>{esc(r['id'])} 第{r['version']}版 {esc(r['business'])}</b> "
                f"{chip(r['priority'], 'info')}{chip(r['status'], 'ok' if r['status'] == '確定' else 'muted', r['status'] == '下書き')}",
                unsafe_allow_html=True)
    st.markdown(f"<div class='rp-quote'>{esc(r['rules'] or r['workflow'])}</div>", unsafe_allow_html=True)
    dg = rules.current_diagnosis(p, r["id"])
    if not dg:
        st.info("まだ診断がありません。画面上部の「AIで診断する」で診断してください。")
        return
    stale = diagnosis_stale_reasons(p, dg)
    st.markdown(category_chip(dg["category"]) + review_chip(dg["review_status"], dg["origin"])
                + (chip("再確認が必要", "bad") if stale else "")
                + f"<span class='rp-small'>{esc(dg['id'])}（要件 第{dg['req_version']}版に対する診断）</span>",
                unsafe_allow_html=True)
    for s in stale:
        st.warning("再確認が必要：" + s)
    for a in dg.get("auto_adjustments", []):
        st.caption("自動調整：" + a)
    st.markdown(f"**理由**：{esc(dg['reason'])}", unsafe_allow_html=True)
    section(f"根拠と原文（{len(dg['evidence'])}件・引用部分に印）")
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
    section("満たす条件・残る条件")
    def col(title, items):
        li = "".join(f"<li>{esc(x)}</li>" for x in items) or "<li>なし</li>"
        return f"<div><div class='h'>{esc(title)}</div><ul>{li}</ul></div>"

    # 3列の間に薄い縦線を入れて読みやすくする（CSS：.rp-cond3）
    st.markdown("<div class='rp-cond3'>" + col("満たす条件", dg["met_conditions"])
                + col("残る条件（ベンダー確認が必要）", dg["remaining_conditions"])
                + col("実機テストで確認すること", dg.get("test_conditions", [])) + "</div>", unsafe_allow_html=True)
    if dg.get("plan_conditions"):
        st.markdown(chip("プラン・オプション条件", "warn") + esc(dg["plan_conditions"]), unsafe_allow_html=True)
    if dg.get("constraints"):
        st.caption("制約：" + dg["constraints"])
    st.markdown(f"**次に確認すること**：{esc(dg.get('next_check') or '未記入')}", unsafe_allow_html=True)

    if dg.get("rejected_evidence"):
        with st.expander(f"検証で除外したAIの引用（{len(dg['rejected_evidence'])}件）"):
            for ev in dg["rejected_evidence"]:
                st.markdown(f"- 参照 {esc(ev.get('ref') or ev.get('seg_id') or ev.get('utt_id'))}：『{esc(ev.get('quote'))}』",
                            unsafe_allow_html=True)
    probs = (dg.get("validation") or {}).get("problems", [])
    for pr in probs:
        st.error(pr)

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

    with box():
        section("人が確認する")
        c1, c2 = st.columns([2, 1])
        cat = c1.selectbox("診断区分", DIAG_CATEGORIES, index=DIAG_CATEGORIES.index(dg["category"]),
                           key=f"form_cat_{dg['id']}")
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

    olds = [d for d in p["diagnoses"] if d["req_id"] == r["id"] and d.get("superseded_by")]
    if olds:
        with st.expander(f"以前の診断（{len(olds)}件・最新には流用しません）"):
            for d in olds:
                st.markdown(f"{category_chip(d['category'])}<span class='rp-small'>{esc(d['id'])} 要件第{d['req_version']}版／"
                            f"{esc(d['origin'])}／{esc(d['created_at'])}：{esc(d['reason'])}</span>", unsafe_allow_html=True)
    candidates(p, r, pid)


def manual(p, r, base):
    key = f"form_man_{r['id']}"
    staged = st.session_state.setdefault(key + "_ev", [])
    cat = st.selectbox("診断区分", DIAG_CATEGORIES, key=key + "_cat",
                       index=DIAG_CATEGORIES.index(base["category"]) if base else 4)
    reason = st.text_area("理由", key=key + "_reason", value=base["reason"] if base else "", height=60)
    c1, c2 = st.columns(2)
    met = c1.text_area("満たす条件（1行に1つ）", key=key + "_met", height=60,
                       value="\n".join(base["met_conditions"]) if base else "")
    rem = c2.text_area("残る条件（1行に1つ）", key=key + "_rem", height=60,
                       value="\n".join(base["remaining_conditions"]) if base else "")
    plan = st.text_input("プラン・オプション等の条件", key=key + "_plan", value=base.get("plan_conditions", "") if base else "")
    nxt = st.text_input("次に確認すること", key=key + "_next", value=base.get("next_check", "") if base else "")
    st.caption(f"根拠：{len(staged)}件（下で追加）" + ("　※既存診断の根拠は引き継がれます" if base else ""))
    ev = evidence_picker.pick(p, key + "_pick")
    c1, c2 = st.columns(2)
    if ev and c1.button("根拠を追加", key=key + "_add"):
        staged.append(ev)
        st.rerun()
    if c2.button("手動の診断として保存", key=key + "_save", type="primary"):
        evs = (base["evidence"] if base else []) + staged
        dg = rules.add_diagnosis(p, {"req_id": r["id"], "product_id": state.product_id(), "category": cat, "reason": reason,
                                     "met_conditions": [x for x in met.splitlines() if x.strip()],
                                     "remaining_conditions": [x for x in rem.splitlines() if x.strip()],
                                     "evidence": evs, "plan_conditions": plan, "next_check": nxt}, origin="手動")
        st.session_state[key + "_ev"] = []
        probs = dg["validation"]["problems"]
        state.flash(f"{dg['id']} を作成しました（未確認）。" + (" 注意：" + " / ".join(probs) if probs else ""))
        st.rerun()


def candidates(p, r, pid):
    with st.expander("関連しそうな箇所を検索する（AIを使わない・料金なし）"):
        st.caption("文字の一致で探した候補です。見つからないことは「機能がない」ことを意味しません。")
        hits = keyword_candidates_report(p, r["id"], pid)
        if not hits:
            st.info("一致する箇所は見つかりませんでした（機能がないとは限りません。ベンダーへの確認を検討してください）。")
        for h in hits[:12]:
            if h["ref_type"] == "source":
                st.markdown(f"<span class='rp-small'>{esc(h['source_name'])}／{esc(h['loc_label'])}"
                            f"{'（周辺）' if h.get('context_of') else ''}</span><div class='rp-quote'>{esc(h['text'][:300])}</div>",
                            unsafe_allow_html=True)
            else:
                st.markdown(f"<span class='rp-small'>録画 {esc(h['rec_id'])}／{fmt_ts(h.get('start'))}／{esc(h.get('speaker_role'))}"
                            f"{'（前後の発言）' if h.get('context_of') else ''}</span><div class='rp-quote'>{esc(h['text'][:300])}</div>",
                            unsafe_allow_html=True)


def ai_section(p, reqs, default: list | None = None, title: str = "AIで診断する",
               button_label: str = "AIで診断する"):
    """AIによる診断（有料）。対象の要件・送信内容・費用見込みを示してから実行する。"""
    s = state.settings()
    confirmed = [r for r in reqs if r["status"] == "確定"]
    section(title)
    if not confirmed:
        st.caption("確定した要件がありません。② 自社のルールで要件を確定すると、診断できます。")
        return
    ids = [r["id"] for r in confirmed]
    lim = s.limits.max_requirements_per_diagnosis
    sel = st.multiselect(f"診断する要件（確定済み・1回最大{lim}件）", ids,
                         default=[x for x in (default or []) if x in ids][:lim], max_selections=lim,
                         key=f"form_ai_diag_reqs_{button_label}")
    if not sel:
        st.caption("診断する要件を選んでください。")
        return
    prompt, refmap, cov = build_diagnosis_input(p, sel, state.product_id(), s)
    nohit = [k for k, v in cov.items() if v == 0]
    if nohit:
        st.caption("関連箇所が見つからない要件：" + "、".join(nohit) + "（AIには「抜粋なし」と伝え、情報不足として扱わせます）")
    client = ai_panel(f"diag_{button_label}", f"{len(sel)}件の要件の診断", prompt, s.limits.max_ai_output_tokens,
                      ["要件", f"資料・発言の抜粋{len(refmap)}件"], button_label=button_label)
    if client:
        run_ai(lambda: run_diagnosis(p, sel, state.product_id(), client, s, state.ledger(),
                                     st.session_state.get("access_code", "")),
               "{n}件の要件を診断しました。根拠を確認してください。")
