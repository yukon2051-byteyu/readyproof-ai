"""トップページ：何のアプリかを伝え、すぐにデモを試せる構成。

1. 見出し帯（左：何をするアプリか／右：照合の流れを示す説明図）
2. 3分デモの選択と開始
3. AIと人の役割分担
4. 使い方の流れ
5. 自社の案件で試す（AIパスワードが必要）

見出し帯の図は説明用の静的なイメージで、実際の診断結果ではない。件数や判定は載せない。
見出し帯の2つのボタンはページ内リンクで、下のセクションへ移動するだけ（デモを勝手に始めない）。
"""
from __future__ import annotations

import streamlit as st

from ...ai.client import valid_access_codes
from ...core import new_project
from ...demos.builder import DEMOS, build
from .. import state
from ..components import start_tour
from ..layout import scroll_top_on_page_change
from ..theme import esc, section

ANCHOR_DEMO = "rp-demo"
ANCHOR_OWN = "rp-own"


def _svg(body: str, cls: str = "ic") -> str:
    return f'<svg class="{cls}" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">{body}</svg>'


STROKE = 'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'
IC_DOC = _svg(f'<path d="M6 3h8l4 4v14H6z" {STROKE}/><path d="M14 3v4h4M9 12h6M9 16h6" {STROKE}/>')
IC_CHART = _svg(f'<path d="M6 3h8l4 4v14H6z" {STROKE}/><path d="M9.5 17v-3M12 17v-6M14.5 17v-4" {STROKE}/>')
IC_CHECK = _svg(f'<circle cx="12" cy="12" r="9" {STROKE}/><path d="M8 12.5l2.7 2.7L16 9.5" {STROKE}/>', "ic ok")
IC_WARN = _svg(f'<path d="M12 4l9 16H3z" {STROKE}/><path d="M12 10v4M12 17h.01" {STROKE}/>', "ic warn")
IC_LIST = _svg(f'<path d="M9 7h11M9 12h11M9 17h11" {STROKE}/><path d="M4.5 7h.01M4.5 12h.01M4.5 17h.01" {STROKE}/>', "ic list")
IC_ARROW = ('<svg class="arw" viewBox="0 0 20 14" fill="none" aria-hidden="true" focusable="false">'
            f'<path d="M1 7h17M12 2l6 5-6 5" {STROKE}/></svg>')
IC_MARK = ('<svg class="mark" viewBox="0 0 34 20" aria-hidden="true" focusable="false"><path d="M9 0h9L9 20H0z" fill="#2BE6F2"/>'
           '<path d="M24 0h10l-9 20H15z" fill="#3B9DFF"/></svg>')
IC_LINK = ('<svg class="link" viewBox="0 0 200 20" preserveAspectRatio="none" fill="none" aria-hidden="true" focusable="false">'
           '<path d="M50 0v4q0 5 5 5h90q5 0 5-5V0M100 9v10M96 15l4 4 4-4" stroke="currentColor" stroke-width="2" '
           'stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg>')
RULES = '<span class="rule" aria-hidden="true"></span><span class="rule" aria-hidden="true"></span>'

HERO_VISUAL = (
    '<div class="viz"><div class="docs">'
    f'<div class="doc"><div class="dt">{IC_DOC}<span>製品資料</span></div>{RULES}</div>'
    f'<div class="doc"><div class="dt">{IC_DOC}<span>社内ルール</span></div>{RULES}</div></div>'
    f'{IC_LINK}'
    f'<div class="diag"><div class="ttl">{IC_CHART}<span class="name2">適合性診断</span><span class="note">診断結果のイメージ</span></div>'
    '<div class="lead">適合性・確認事項を整理</div>'
    f'<ul><li>{IC_CHECK}適合項目</li><li>{IC_WARN}要確認事項</li><li>{IC_LIST}受入テスト項目</li></ul>'
    '</div></div>')

FLOW = [("入力1", "製品の資料", "提案書・機能一覧・マニュアル・営業説明など"),
        ("入力2", "自社のルール", "質問に答え、ルール・例外・条件をまとめる"),
        ("出力1", "診断結果", "要件ごとに、そのまま使えるかを根拠付きで判定"),
        ("出力2", "受入テスト", "実機で確認すべき項目をテスト仕様書に"),
        ("判断", "導入判断", "テスト結果と残った問題を見て、人が導入を決める")]
ROLES = [
    ("AI", "AIが行うこと", "資料の照合・診断、確認事項やテスト仕様書案の作成"),
    ("人", "人が行うこと", "AIの結果を確認し、実機でテストして最終判断"),
]


def _open_demo(demo_id: str) -> None:
    with st.spinner("サンプル資料を、実際の読込機能で読み込んでいます…"):
        p = build(demo_id)
    state.set_project(p, demo_initial=p)
    start_tour(demo_id)


def _hero() -> None:
    st.markdown(
        '<div class="rp-herowrap"><div class="rp-hero"><div class="copy">'
        f'<div class="top"><div class="eyebrow">AI受入テスト・導入確認支援</div><div class="name">{IC_MARK}<span>ReadyProof AI</span></div></div>'
        '<div class="tag" role="heading" aria-level="1"><span>その製品、</span><span><em>ウチ</em>で使える？</span></div>'
        '<p class="desc"><span>製品資料と社内ルールを照合し、</span><span>導入判断と受入テストの準備を支援。</span></p>'
        '<p class="sub"><span>AIが確認事項を整理し、</span><span>最終的な導入判断は人が行います。</span></p>'
        f'<div class="cta"><a class="btn primary" href="#{ANCHOR_DEMO}">3分デモを体験する{IC_ARROW}</a>'
        f'<a class="btn ghost" href="#{ANCHOR_OWN}">自社の案件で試す</a></div>'
        f'</div>{HERO_VISUAL}</div></div>', unsafe_allow_html=True)


def _demo() -> None:
    section("まずは3分デモで体験", size="md", anchor=ANCHOR_DEMO)
    # デモは保存済みの結果を表示するだけで、AIパスワードを確認しない（_open_demo を参照）
    st.markdown("<div class='rp-lead'>サンプルデータで、診断から導入判断までの流れを確認できます。パスワードは不要です。</div>",
                unsafe_allow_html=True)
    titles = {d["id"]: d["title"] for d in DEMOS}
    c1, c2 = st.columns([1.5, 1], vertical_alignment="bottom")
    pick = c1.selectbox("見たいデモを選ぶ", list(titles.keys()), format_func=lambda i: titles[i], key="demo_pick")
    if c2.button("3分デモを始める", type="primary", icon=":material/play_arrow:", width="stretch", key="open_main"):
        _open_demo(pick)
    d = next(x for x in DEMOS if x["id"] == pick)
    st.markdown(f'<div class="rp-lead">{esc(d["title"])}：{esc(d["theme"])}</div>', unsafe_allow_html=True)


def _roles() -> None:
    section("AIと人の役割分担", size="md")
    cards = "".join(f'<div class="rp-card role"><div class="t"><span class="rp-num">{esc(m)}</span>{esc(t)}</div>'
                    f'<div class="b">{esc(x)}</div></div>' for m, t, x in ROLES)
    st.markdown(f'<div class="rp-grid" style="--cols:2">{cards}</div>', unsafe_allow_html=True)


def _flow() -> None:
    section("使い方の流れ", size="md")
    cards = "".join(f'<div class="rp-card"><div class="t"><span class="rp-num">{i + 1}</span>{esc(t)}</div>'
                    f'<div class="m in">{esc(io)}</div><div class="b">{esc(d)}</div></div>'
                    for i, (io, t, d) in enumerate(FLOW))
    st.markdown(f'<div class="rp-flow5">{cards}</div>', unsafe_allow_html=True)


def _own() -> None:
    section("自社の案件で試す", size="md", anchor=ANCHOR_OWN)
    st.markdown("<div class='rp-lead'>AIの実行には料金がかかるため、AIパスワードが必要です（デモには必要ありません）。</div>",
                unsafe_allow_html=True)
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


def render():
    scroll_top_on_page_change("home")  # ロゴ・サイドバー・「ホームへ」のどれで戻っても、最上部から表示する
    _hero()
    _demo()
    _roles()
    _flow()
    _own()
