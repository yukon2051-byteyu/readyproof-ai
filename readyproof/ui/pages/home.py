"""トップページ：何をするアプリか → ガイド付きデモ（約4分）→ 自分の案件で使う。"""
from __future__ import annotations

import streamlit as st

from ...config import APP_NAME_EN, APP_NAME_JA, DESCRIPTION, TAGLINE
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
DEMO_POINTS = {
    "demo1": ["スライドの表から根拠を引用", "記載なし → 質問 → 回答で更新", "境界値テストの不合格 → 設定変更 → 再テスト"],
    "demo2": ["「ロット管理 ○」だけで判断しない", "対応方法を比べて改修依頼書", "一部合格を全体の合格にしない"],
    "demo3": ["録画の発言を時刻・話者付きで根拠に", "資料と営業説明の矛盾を表示", "口頭説明を書面で確認する質問"],
}


def _cards(items: list[str]) -> None:
    st.markdown(f'<div class="rp-grid" style="--cols:{len(items)}">{"".join(items)}</div>', unsafe_allow_html=True)


def render():
    st.markdown(
        f'<div class="rp-hero"><div class="eyebrow">{esc(APP_NAME_JA)}</div>'
        f'<div class="name">{esc(APP_NAME_EN)}</div><div class="tag">{esc(TAGLINE)}</div>'
        f'<div class="desc">{esc(SHORT)}</div></div>', unsafe_allow_html=True)

    _cards([f'<div class="rp-card"><div class="t">{i + 1}. {esc(t)}</div><div class="b">{esc(b)}</div></div>'
            for i, (t, b) in enumerate(WHAT)])

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

    with st.expander("このアプリについて（役割分担・データの扱い）"):
        st.write(DESCRIPTION)
        st.markdown(
            "**役割分担**\n"
            "- AI：要件の分割、関連箇所の照合と診断、質問・対応案、依頼書とテストのたたき台（すべて下書き）\n"
            "- プログラム：読込と参照位置、文字起こしの制御、版と状態の管理、引用の実在確認、古い根拠の検出、集計、費用管理\n"
            "- 人：要件・話者・発言・診断・回答・依頼・テストの確定、実機テスト、導入判断\n\n"
            "**データの扱い**\n"
            "- 公開環境では、外部送信が許可された資料・録画や、匿名化した情報だけを使ってください。録画は参加者の利用許可を確認してください\n"
            "- AI に文字を送る前に、送信先と内容を表示します。資料や発言の中の命令は、アプリへの指示として扱いません\n"
            "- 認証はありません。作業者名は自己申告で、本人確認や正式な承認ではありません")
