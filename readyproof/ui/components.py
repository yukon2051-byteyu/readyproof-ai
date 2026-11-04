"""画面部品（作業位置の表示、根拠の表示、AI 実行パネル など）。"""
from __future__ import annotations

import streamlit as st

from ..ai.client import ClaudeClient, paid_ai_blockers
from ..ai.tasks import estimate_cost_jpy
from ..core import primary_product
from ..logic.evidence import VALIDITY_NOTE, evidence_label, validate_evidence
from . import state
from .theme import chip, esc

STEPS = [("sources", "1 製品の資料・営業説明"), ("requirements", "2 自社の仕事・ルール"), ("diagnosis", "3 自社に合うかを確認"),
         ("questions", "4 質問・対応依頼"), ("tests", "5 試すこと・実施結果"), ("decision", "6 残った問題と導入判断")]


def context_bar(current: str) -> None:
    """現在の案件・製品・作業位置。"""
    p = state.project()
    if not p:
        return
    prod = primary_product(p) or {}
    demo = chip("架空のデモ", "warn") if p["project"].get("demo_id") else ""
    steps = "".join(f'<span class="rp-step{" on" if k == current else ""}">{esc(lbl)}</span>' for k, lbl in STEPS)
    st.markdown(
        f'<div class="rp-ctx"><span>案件 <b>{esc(p["project"]["name"])}</b></span>'
        f'<span>製品 <b>{esc(prod.get("name", "未登録"))}</b>／プラン <b>{esc(prod.get("plan", "未記入") or "未記入")}</b></span>'
        f'{demo}<span class="rp-steps">{steps}</span></div>', unsafe_allow_html=True)


def page_title(title: str, help_text: str = "") -> None:
    st.subheader(title)
    if help_text:
        st.caption(help_text)


def evidence_view(p: dict, ev: dict, product_id: str | None, idx: int | None = None) -> dict:
    """根拠1件：表示＋検証結果。"""
    v = validate_evidence(p, ev, product_id)
    kind = ev.get("kind", "")
    head = chip(kind or "根拠", "info")
    if not v["ok"]:
        head += chip("検証エラー", "bad")
    elif v["warnings"]:
        head += chip("要注意", "warn")
    else:
        head += chip("引用の実在を確認", "ok")
    label = evidence_label(p, ev, with_quote=False)
    st.markdown(f'{head}<span class="rp-small">{esc(label)}</span>', unsafe_allow_html=True)
    if ev.get("quote"):
        st.markdown(f'<div class="rp-quote">『{esc(ev["quote"])}』</div>', unsafe_allow_html=True)
    for e in v["errors"]:
        st.markdown(f'<div class="rp-small" style="color:#8A1C1C">エラー：{esc(e)}</div>', unsafe_allow_html=True)
    for w in v["warnings"]:
        st.markdown(f'<div class="rp-small" style="color:#7A4B00">注意：{esc(w)}</div>', unsafe_allow_html=True)
    return v


def validity_note() -> None:
    st.caption(VALIDITY_NOTE)


def empty(msg: str, action_label: str | None = None, page_key: str | None = None) -> None:
    st.info(msg)
    if action_label and page_key and st.button(action_label, key=f"empty_{page_key}_{action_label}"):
        state.goto(page_key)


def name_required() -> str | None:
    n = state.user_name()
    if not n:
        st.warning("確定・確認の操作には、サイドバーで作業者名（自己申告）を入力してください。")
        return None
    return n


def run_ai(fn, success_msg: str):
    """AI 実行（二重実行防止・失敗時も入力を保持）。fn は作成物のリストを返す。"""
    from ..ai.client import AIError

    st.session_state.ai_busy = True
    try:
        with st.spinner("AI が下書きを作成しています…（画面を閉じずにお待ちください）"):
            created = fn()
        state.flash(success_msg.format(n=len(created) if isinstance(created, list) else 1))
    except AIError as e:
        st.session_state.ai_busy = False
        st.error(f"{e}（入力内容と手動機能はそのまま使えます）")
        return None
    finally:
        st.session_state.ai_busy = False
    st.rerun()


def ai_panel(key: str, task_label: str, preview_text: str, max_tokens: int, details: list[str]):
    """AI 実行前の確認パネル。実行可能なら AI クライアントを返す（ボタンが押されたとき）。

    デモ案件では有料処理を使わない。送信先・対象・費用見込みを事前に表示する。
    """
    s = state.settings()
    with st.container(border=True):
        st.markdown(f"**AIで下書きを作る：{task_label}**")
        if state.is_demo():
            st.info("デモでは有料のAI処理を使いません（表示中の結果は「準備済みのデモ結果」です）。新しい案件で利用できます。")
            return None
        est = estimate_cost_jpy(len(preview_text), max_tokens, s.budget)
        st.markdown(
            f"- 送信先：Anthropic 社の Claude API（モデル {esc(s.budget.model)}）\n"
            f"- 送る内容：{'、'.join(details)}（約{len(preview_text):,}字）。未選択の箇所・ノート・発言は送りません\n"
            f"- 費用見込み：最大 約{est['jpy']:,.0f}円（{est['note']}）\n"
            f"- 結果はすべて「AI下書き」として登録され、人が確認するまで確定しません")
        with st.expander("送信する内容を確認する"):
            st.text(preview_text[:6000] + ("\n…（以下省略）" if len(preview_text) > 6000 else ""))
        blockers = paid_ai_blockers(s, st.session_state.get("access_code", ""))
        lg = state.ledger()
        if lg and not blockers:
            summ = lg.summary(st.session_state.get("access_code", ""))
            st.caption(f"今月の利用：AI生成 {summ['code']['ai_runs']}/{s.budget.ai_runs_per_code_per_month} 回（この利用コード）、"
                       f"アプリ全体 {summ['all']['cost_jpy']:,.0f}/{s.budget.monthly_budget_jpy:,} 円")
        if blockers:
            for b in blockers:
                st.caption(f"実行できません：{b}")
            return None
        ok = st.checkbox("送信先と内容を確認しました（外部送信が許可された情報だけです）", key=f"ai_ok_{key}")
        busy = st.session_state.get("ai_busy", False)
        if st.button("AIで下書きを作る", key=f"ai_run_{key}", type="primary", disabled=not ok or busy,
                     icon=":material/auto_awesome:"):
            return ClaudeClient(s)
    return None
