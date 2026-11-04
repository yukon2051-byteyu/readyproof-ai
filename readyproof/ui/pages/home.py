"""トップページ。"""
from __future__ import annotations

import streamlit as st

from ...config import APP_NAME_EN, APP_NAME_JA, DESCRIPTION, TAGLINE
from ...core import new_project
from ...demos.builder import DEMOS, build
from ...export.jsonio import LoadError, from_json_bytes
from .. import state
from ..theme import esc

FLOW = [
    ("1 製品の資料・営業説明", "PDF・Word・Excel・PowerPoint・録画を登録し、読めた範囲と発言を確認"),
    ("2 自社の仕事・ルール", "業務ルール・作業手順・必須条件を要件として確定"),
    ("3 自社に合うかを確認", "AIが照合候補を作り、人が根拠と診断を確認"),
    ("4 質問・対応依頼", "不明点をベンダーへの質問に。合わない部分は対応方法と依頼書へ"),
    ("5 試すこと・実施結果", "受入テストを確定し、人が実機で試して結果を記録・再テスト"),
    ("6 残った問題と導入判断", "残件と根拠を確認し、人が導入可否を判断"),
]


def render():
    st.markdown(
        f'<div class="rp-hero"><h1>{esc(APP_NAME_EN)}</h1><p class="ja">{esc(APP_NAME_JA)}</p>'
        f'<p class="tag">{esc(TAGLINE)}</p></div>', unsafe_allow_html=True)
    st.write(DESCRIPTION)

    st.markdown("#### 3分で分かるデモ（架空のデータ・料金なし）")
    cols = st.columns(3)
    for col, d in zip(cols, DEMOS):
        with col, st.container(border=True):
            st.markdown(f"**{d['title']}**")
            st.caption(f"業務：{d['business']}")
            st.write(d["theme"])
            with st.expander("見どころ"):
                for h in d["highlights"]:
                    st.markdown(f"- {h}")
                st.caption(f"強み：{d['strength']}")
            if st.button("このデモを開く", key=f"open_{d['id']}", type="primary", icon=":material/play_arrow:",
                         width="stretch"):
                with st.spinner("サンプル資料を実際の読込機能で読み込んでいます…"):
                    p = build(d["id"])
                state.set_project(p, demo_initial=p)
                state.flash(f"デモ「{d['title']}」を開きました。AIの結果は「準備済みのデモ結果」です。")
                state.goto(d["start_page"])

    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        st.markdown("**新しい案件を作る**")
        name = st.text_input("案件名", placeholder="例：勤怠管理サービスの導入", key="new_project_name")
        if st.button("作成して案件・製品の登録へ", icon=":material/add:", disabled=not name.strip()):
            state.set_project(new_project(name.strip()))
            state.flash("新しい案件を作成しました。まず製品情報を登録してください。")
            state.goto("project")
    with c2, st.container(border=True):
        st.markdown("**保存した案件を読み込む**")
        up = st.file_uploader("ReadyProof AI で保存した JSON", type=["json"], key="home_load")
        if up is not None and st.button("読み込む", icon=":material/upload_file:"):
            try:
                p = from_json_bytes(up.getvalue())
            except LoadError as e:
                st.error(f"読み込めませんでした：{e}（現在の作業はそのままです）")
            else:
                state.set_project(p)
                state.flash("案件を読み込みました。録画・資料の元ファイルは含まれていません。")
                state.goto("decision")

    st.markdown("#### 資料・録画からテストまでの流れ")
    st.markdown('<div class="rp-flow">' + "".join(f"<div><b>{esc(a)}</b>{esc(b)}</div>" for a, b in FLOW) + "</div>",
                unsafe_allow_html=True)

    with st.expander("AI・プログラム・人の役割分担"):
        a, b, c = st.columns(3)
        a.markdown("**AI（下書き）**\n- 要件の分割候補\n- 関連箇所の照合と診断候補\n- 質問・対応案の整理\n- 依頼書とテストのたたき台")
        b.markdown("**プログラム（確実な処理）**\n- 読込と参照位置の保持\n- 文字起こしの制御\n- ID・版・状態の管理\n- 引用の実在確認\n- 古い根拠の検出・集計\n- 利用回数と費用の管理")
        c.markdown("**人（判断）**\n- 要件・話者・発言内容の確定\n- 診断と根拠の意味の確認\n- 回答・対応・依頼の確定\n- テストの確定と実施\n- 導入可否の判断")
    with st.expander("データの取り扱い"):
        st.markdown(
            "- 公開環境では、外部送信が許可された資料・録画、または匿名化した情報だけを使ってください。\n"
            "- 録画を使う前に、参加者から録画・発言の利用許可を得ていることを確認してください。\n"
            "- アップロード（このアプリ内）／音声の処理（このサーバー内・外部送信なし）／文字のAI送信（Claude API）は別の操作で、"
            "AI送信の前に送信先と内容を表示します。\n"
            "- 資料や発言の中に書かれた命令は、アプリへの指示として扱いません。マクロ・埋め込み・外部リンクは実行しません。\n"
            "- 認証はありません。作業者名は自己申告で、正式な承認や本人確認ではありません。")
