"""トップページ：3分で価値が伝わる構成。

1. 見出し帯（何をするアプリか）
2. 4段階（入力2つ → 出力2つ）と、3分デモの開始ボタン
3. できること・役割分担
4. 3件のデモの選択
5. 自分の案件で試してみる
"""
from __future__ import annotations

import streamlit as st

from ...config import APP_NAME_JA
from ...ai.client import valid_access_codes
from ...core import new_project
from ...demos.builder import DEMOS, build
from .. import state
from ..components import start_tour
from ..theme import esc, section

# 見出し帯のモチーフ：「根拠を確かめた書類」（書類＋引用の行＋チェック）
MOTIF = (
    '<svg class="motif" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
    '<rect x="38" y="18" width="104" height="136" rx="12" fill="none" stroke="#38BDF8" stroke-opacity=".35" stroke-width="4"/>'
    '<rect x="54" y="42" width="56" height="7" rx="3.5" fill="#FFFFFF" fill-opacity=".35"/>'
    '<rect x="54" y="60" width="72" height="7" rx="3.5" fill="#FFFFFF" fill-opacity=".22"/>'
    '<rect x="54" y="78" width="64" height="7" rx="3.5" fill="#FFFFFF" fill-opacity=".22"/>'
    '<rect x="50" y="96" width="4" height="26" rx="2" fill="#38BDF8" fill-opacity=".8"/>'
    '<rect x="60" y="100" width="58" height="6" rx="3" fill="#38BDF8" fill-opacity=".45"/>'
    '<rect x="60" y="112" width="44" height="6" rx="3" fill="#38BDF8" fill-opacity=".45"/>'
    '<circle cx="142" cy="146" r="34" fill="#38BDF8"/>'
    '<path d="M126 147 l11 11 l22 -24" fill="none" stroke="#14263F" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>'
    '</svg>')

FLOW = [("入力1", "製品の資料", "提案書・機能一覧・マニュアル・営業説明など"),
        ("入力2", "自社のルール", "質問に答え、ルール・例外・条件をまとめる"),
        ("出力1", "診断結果", "要件ごとに、そのまま使えるかを根拠付きで判定"),
        ("出力2", "受入テスト", "実機で確認すべき項目をテスト仕様書に"),
        ("判断", "導入判断", "テスト結果と残った問題を見て、人が導入を決める")]
ROLES = [
    ("AI", "AI", "照合・診断・テスト仕様書", "資料と自社のルールの照合・診断、ベンダーへの質問、依頼書とテスト仕様書"),
    ("人", "人", "判断・テスト", "AIの診断の確認、導入判断、実機でのテスト"),
]


def _grid(items: list[str], cols: int | None = None) -> None:
    st.markdown(f'<div class="rp-grid" style="--cols:{cols or len(items)}">{"".join(items)}</div>', unsafe_allow_html=True)


def _open_demo(demo_id: str) -> None:
    with st.spinner("サンプル資料を、実際の読込機能で読み込んでいます…"):
        p = build(demo_id)
    state.set_project(p, demo_initial=p)
    start_tour(demo_id)


def render():
    st.markdown(
        f'<div class="rp-hero">{MOTIF}<div class="inner"><div class="eyebrow">{esc(APP_NAME_JA)}</div>'
        '<div class="name">ReadyProof <span>AI</span></div>'
        '<div class="tag"><em>「うちの会社で使える？」</em>に答える<em>AI</em></div>'
        '<div class="desc">製品の情報と自社の業務ルールを照合し、受入テスト・導入判断までつなげます。</div>'
        '</div></div>', unsafe_allow_html=True)

    section("AIと人の役割分担", top="-7px", gold=True)  # 上の余白を0.7cm詰める
    _grid([f'<div class="rp-card role"><div class="t"><span class="rp-num">{esc(m)}</span>{esc(d)}</div>'
           f'<div class="b">{esc(x)}</div></div>' for m, w, d, x in ROLES])

    # ---- 3分デモ：開始 → 流れ → 成果物 ----
    section("使い方の流れ", top="4.3px")  # 上の余白：当初より0.4cm短い（0.7cm詰めて0.3cm戻す）
    _grid([f'<div class="rp-card"><div class="t"><span class="rp-num">{i + 1}</span>{esc(t)}</div>'
           f'<div class="m in" style="margin-top:0;padding-top:0">{esc(io)}</div>'
           f'<div class="b">{esc(d)}</div></div>'
           for i, (io, t, d) in enumerate(FLOW)])

    # ---- 3分デモ：その場で選んで始める ----
    titles = {d["id"]: d["title"] for d in DEMOS}
    c1, c2 = st.columns([1.5, 1], vertical_alignment="bottom")
    pick = c1.selectbox("見たいデモを選ぶ", list(titles.keys()), format_func=lambda i: titles[i], key="demo_pick")
    if c2.button("3分デモを始める", type="primary", icon=":material/play_arrow:", width="stretch", key="open_main"):
        _open_demo(pick)
    d = next(x for x in DEMOS if x["id"] == pick)
    st.markdown(f'<div class="rp-small">{esc(d["title"])}：{esc(d["theme"])}</div>', unsafe_allow_html=True)

    # ---- 自分の案件 ----
    section("自分の案件で試してみる", big=True)
    st.markdown("<div class='rp-small'>AIパスワードが必要です（AIの実行には料金がかかるため）。</div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([2, 1.3, 1], vertical_alignment="bottom")
    name = c1.text_input("案件名", placeholder="例：勤怠管理サービスの導入", key="new_project_name")
    code = c2.text_input("AIパスワード", type="password", key="home_ai_pw", value=st.session_state.get("access_code", ""))
    pw_ok = bool(code.strip()) and code.strip() in valid_access_codes()
    if pw_ok:
        st.session_state.access_code = code  # AIを実行する画面でも使う
    elif code.strip():
        st.caption(":red[AIパスワードが正しくありません。]")
    if c3.button("作成する", icon=":material/add:", disabled=not (name.strip() and pw_ok), width="stretch"):
        state.set_project(new_project(name.strip()))
        state.flash("新しい案件を作成しました。まず製品の情報と資料を入れてください。")
        state.goto("input1")
