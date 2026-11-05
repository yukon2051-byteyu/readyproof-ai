"""③ 診断結果の部品：AI診断の実行欄と、関連箇所の検索。画面の本体は step3.py・diagnosis_panels.py。"""
from __future__ import annotations

import streamlit as st

from ...ai.tasks import build_diagnosis_input, keyword_candidates_report, run_diagnosis
from ...media.subtitles import fmt_ts
from .. import state
from ..components import ai_panel, run_ai
from ..theme import esc, section


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
