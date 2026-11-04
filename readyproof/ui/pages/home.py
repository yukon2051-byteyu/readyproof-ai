"""トップページ：何をするアプリか → ガイド付きデモ（約4分）→ 自分の案件で使う。"""
from __future__ import annotations

import streamlit as st

from ...config import APP_NAME_JA, TAGLINE
from ...core import new_project
from ...demos.builder import DEMOS, build
from ...export.jsonio import LoadError, from_json_bytes
from .. import state
from ..components import start_tour
from ..theme import esc, section

SHORT = "製品の資料や営業説明と、自社の業務ルールを根拠付きで照合し、質問・依頼書・受入テスト・導入判断までつなげます。"

WHAT = [
    ("照合する", "資料のページ・スライドや営業の発言時刻を根拠に、自社のルールに合うかを6区分で整理します。"),
    ("確認・依頼する", "不明点はベンダーへの質問に、合わない部分は対応方法を比べて改修・設定変更の依頼書にします。"),
    ("試して判断する", "受入テストを人が実機で試して記録し、残った問題を見ながら人が導入を判断します。"),
]
ROLES = [
    ("AI", "AI", "下書きを作る", "要件の分割、関連箇所の照合と診断、質問・対応案、依頼書とテストのたたき台"),
    ("PG", "プログラム", "確実に処理する", "読込と参照位置、版と状態の管理、引用の実在確認、古い根拠の検出、集計"),
    ("人", "人", "確定・判断する", "要件・話者・診断・依頼・テストの確定、実機テスト、導入判断"),
]
DEMO_POINTS = {
    "demo1": ["スライドの表から根拠を引用", "記載なし → 質問 → 回答で更新", "境界値テストの不合格 → 設定変更 → 再テスト"],
    "demo2": ["「ロット管理 ○」だけで判断しない", "対応方法を比べて改修依頼書", "一部合格を全体の合格にしない"],
    "demo3": ["録画の発言を時刻・話者付きで根拠に", "資料と営業説明の矛盾を表示", "口頭説明を書面で確認する質問"],
}


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


def _cards(items: list[str]) -> None:
    st.markdown(f'<div class="rp-grid" style="--cols:{len(items)}">{"".join(items)}</div>', unsafe_allow_html=True)


def render():
    tag = esc(TAGLINE).replace("「うちの会社で使える？」", "<em>「うちの会社で使える？」</em>")
    st.markdown(
        f'<div class="rp-hero">{MOTIF}<div class="inner"><div class="eyebrow">{esc(APP_NAME_JA)}</div>'
        f'<div class="name">ReadyProof <span>AI</span></div><div class="tag">{tag}</div>'
        f'<div class="desc">{esc(SHORT)}</div></div></div>', unsafe_allow_html=True)

    section("このアプリでできること")
    _cards([f'<div class="rp-card"><div class="t"><span class="rp-num">{i + 1}</span>{esc(t)}</div><div class="b">{esc(b)}</div></div>'
            for i, (t, b) in enumerate(WHAT)])
    section("AI・プログラム・人の役割分担")
    _cards([f'<div class="rp-card role"><div class="t"><span class="rp-num">{esc(mark)}</span>{esc(who)}：{esc(does)}</div>'
            f'<div class="b">{esc(detail)}</div></div>' for mark, who, does, detail in ROLES])

    section("ガイド付きデモ（約4分・5ステップ・料金なし）")
    st.caption("架空の会社・製品・資料で、照合から判断までを画面の案内に沿って体験できます。")
    _cards([f'<div class="rp-card"><div class="t">{esc(d["title"])}</div><div class="b">{esc(d["theme"])}</div>'
            f'<ul>{"".join(f"<li>{esc(x)}</li>" for x in DEMO_POINTS[d["id"]])}</ul>'
            f'<div class="m">業務：{esc(d["business"])}</div></div>' for d in DEMOS])
    cols = st.columns(len(DEMOS))
    for col, d in zip(cols, DEMOS):
        if col.button("このデモを始める", key=f"open_{d['id']}", type="primary", icon=":material/play_arrow:",
                      width="stretch"):
            with st.spinner("サンプル資料を、実際の読込機能で読み込んでいます…"):
                p = build(d["id"])
            state.set_project(p, demo_initial=p)
            start_tour(d["id"])

    section("自分の案件で使う")
    t1, t2 = st.tabs(["新しい案件を作る", "保存した案件を開く"])
    with t1:
        c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
        name = c1.text_input("案件名", placeholder="例：勤怠管理サービスの導入", key="new_project_name")
        if c2.button("作成する", icon=":material/add:", disabled=not name.strip(), width="stretch"):
            st.session_state.pop("tour", None)
            state.set_project(new_project(name.strip()))
            state.flash("新しい案件を作成しました。まず製品の情報を登録してください。")
            state.goto("project")
    with t2:
        up = st.file_uploader("ReadyProof AI で保存した JSON ファイル", type=["json"], key="home_load")
        if up is not None and st.button("開く", icon=":material/folder_open:"):
            try:
                p = from_json_bytes(up.getvalue())
            except LoadError as e:
                st.error(f"開けませんでした：{e}（今の作業はそのままです）")
            else:
                st.session_state.pop("tour", None)
                state.set_project(p)
                state.flash("案件を開きました。資料・録画の元ファイルは含まれていません。")
                state.goto("decision")

    st.caption("公開版では、外部に送ってよい資料・録画（または匿名化した情報）だけを使ってください。"
               "認証はなく、作業者名は自己申告です。AI に文字を送る前には、送信先と内容を必ず表示します。")
