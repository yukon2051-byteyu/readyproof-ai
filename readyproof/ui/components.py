"""画面部品（作業位置の表示、根拠の表示、AI 実行パネル など）。"""
from __future__ import annotations

import streamlit as st

from ..ai.client import ClaudeClient, paid_ai_blockers, setup_blockers
from ..ai.tasks import estimate_cost_jpy
from ..core import primary_product
from ..logic.evidence import VALIDITY_NOTE, evidence_label, validate_evidence
from . import state
from .theme import badge, chip, esc, box

STEPS = {"sources": "ステップ1", "requirements": "ステップ2", "diagnosis": "ステップ3", "questions": "ステップ4",
         "tests": "ステップ5", "decision": "ステップ6"}


def context_bar(current: str) -> None:
    """画面上部：ガイド付きデモの帯（デモ中のみ）と、現在の案件・製品（灰色の補足）。"""
    p = state.project()
    if not p:
        return
    prod = primary_product(p) or {}
    demo = "架空のデモ ／ " if p["project"].get("demo_id") else ""
    step = f"{STEPS[current]} ／ " if current in STEPS else ""
    st.markdown(f'<div class="rp-ctx">{esc(step + demo)}{esc(p["project"]["name"])} ／ '
                f'{esc(prod.get("name", "製品未登録"))}（{esc(prod.get("plan") or "プラン未記入")}）</div>',
                unsafe_allow_html=True)


def page_title(title: str, help_text: str = "") -> None:
    """画面名（1段目）と説明（灰色）。番号は上の補足行に出すので、画面名からは外す。"""
    name = title.split(" ", 1)[1] if title[:1].isdigit() and " " in title else title
    st.markdown(f'<div class="rp-title">{esc(name)}</div>'
                + (f'<div class="rp-desc">{esc(help_text)}</div>' if help_text else ""), unsafe_allow_html=True)


# ---------------- ガイド付きデモ ----------------
def start_tour(demo_id: str) -> None:
    """デモを開く：最初の画面（① 製品の資料）へ移り、見てほしい項目を開いておく。"""
    from .layout import apply_demo_state

    p = state.project()
    if p:
        apply_demo_state(p, "input1")
    state.goto("input1")


def _mark(text: str, quote: str) -> str:
    """原文を HTML エスケープし、引用部分に印を付ける（見つからなければ印なし）。"""
    t = esc(text)
    q = esc(quote or "").strip()
    if q and q in t:
        return t.replace(q, f'<mark class="rp-mark">{q}</mark>', 1)
    return t


def evidence_view(p: dict, ev: dict, product_id: str | None, idx: int | None = None) -> dict:
    """根拠1件：どこの何か（1行）＋原文の前後（引用に印）＋問題があれば注意。"""
    from ..logic.evidence import context_rows

    v = validate_evidence(p, ev, product_id)
    head = ""
    if not v["ok"]:
        head = badge("検証エラー", "red", "error")
    elif v["warnings"]:
        head = badge(f"注意 {len(v['warnings'])}件", "orange", "warning")
    label = evidence_label(p, ev, with_quote=False)
    kind = ev.get("kind") or "根拠"
    where = label if label.startswith(kind) else f"{kind}｜{label}"
    st.markdown(f'{head}<span class="rp-small">{esc(where)}</span>', unsafe_allow_html=True)
    rows = context_rows(p, ev) if v["ok"] else []
    if rows:
        html_rows = "".join(
            f'<div class="rp-ctxrow{" hit" if r["target"] else ""}"><div class="loc">{esc(r["loc"])}'
            f'{"<br>" + esc(r["note"]) if r["note"] else ""}</div>'
            f'<div>{_mark(r["text"], ev.get("quote", "")) if r["target"] else esc(r["text"])}</div></div>' for r in rows)
        st.markdown(f'<div class="rp-ctxbox">{html_rows}</div>', unsafe_allow_html=True)
    elif ev.get("quote"):
        st.markdown(f'<div class="rp-quote">『{esc(ev["quote"])}』</div>', unsafe_allow_html=True)
    for e in v["errors"]:
        st.markdown(f":red[エラー：{esc(e)}]")
    if v["warnings"]:
        st.markdown("<span class='rp-small'>" + "<br>".join("注意：" + esc(w) for w in v["warnings"]) + "</span>",
                    unsafe_allow_html=True)
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


def ai_panel(key: str, task_label: str, preview_text: str, max_tokens: int, details: list[str],
             button_label: str = "AIで下書きを作る"):
    """AI 実行前の確認パネル。実行可能なら AI クライアントを返す（ボタンが押されたとき）。

    デモ案件では有料処理を使わない。送信先・対象・費用見込みを事前に表示する。
    """
    s = state.settings()
    with box():
        st.markdown(f"**{button_label}：{task_label}**")
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
        setup = setup_blockers(s)
        if setup:
            st.warning("この環境では、まだAIを実行できません（管理者の設定が必要です）。", icon=":material/lock:")
            for x in setup:
                st.caption(f"管理者向け：{x}")
            return None
        code = st.text_input("AIパスワード", type="password", value=st.session_state.get("access_code", ""),
                             key=f"ai_pw_{key}", help="AIの実行には料金がかかるため、パスワードを知っている人だけが使えます。")
        st.session_state.access_code = code  # 画面を移動しても保持する
        if not code.strip():
            st.caption("AIを実行するには、AIパスワードを入力してください。")
            return None
        blockers = paid_ai_blockers(s, code)
        lg = state.ledger()
        if lg and not blockers:
            try:
                summ = lg.summary(st.session_state.get("access_code", ""))
            except Exception:  # 記録先に届かないときは実行させない（上限を確認できないため）
                st.caption("実行できません：利用記録の保存先に接続できません。時間をおいて再度お試しください。")
                return None
            st.caption(f"今月の利用：AI生成 {summ['code']['ai_runs']}/{s.budget.ai_runs_per_code_per_month} 回（このAIパスワード）、"
                       f"アプリ全体 {summ['all']['cost_jpy']:,.0f}/{s.budget.monthly_budget_jpy:,} 円")
        if blockers:
            for b in blockers:
                st.caption(f"実行できません：{b}")
            return None
        ok = st.checkbox("送信先と内容を確認しました（外部送信が許可された情報だけです）", key=f"ai_ok_{key}")
        busy = st.session_state.get("ai_busy", False)
        if st.button(button_label, key=f"ai_run_{key}", type="primary", disabled=not ok or busy,
                     icon=":material/auto_awesome:"):
            return ClaudeClient(s)
    return None
