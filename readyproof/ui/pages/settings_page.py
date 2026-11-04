"""設定・利用枠の表示。値の変更は環境変数または Streamlit secrets で行う（画面からは変更しない）。"""
from __future__ import annotations

from dataclasses import asdict

import pandas as pd
import streamlit as st

from ...ai.client import get_api_key, paid_ai_blockers
from ...media.transcribe import local_whisper_available
from .. import state
from ..theme import section
from ..components import page_title

LABELS = {
    "max_files_per_upload": "1回に登録できる資料数", "max_file_mb": "資料1件の最大サイズ(MB)",
    "max_unzipped_mb": "Office形式の展開後サイズ上限(MB)", "max_chars_per_source": "資料1件の抽出文字数上限",
    "max_slides": "スライド数上限", "max_pdf_pages": "PDFページ数上限", "max_xlsx_rows_per_sheet": "Excel 1シートの行数上限",
    "max_media_mb": "録画の最大サイズ(MB)", "max_media_minutes": "録画の最大時間(分)",
    "max_transcribe_minutes_per_run": "1回の文字起こし時間(分)", "max_ai_input_chars": "AIへの入力上限(字)",
    "max_ai_output_tokens": "AIの出力上限(トークン)", "max_requirements_per_diagnosis": "診断：1回の最大要件数",
    "max_tests_per_generation": "テスト生成：最大件数", "max_requests_per_generation": "依頼書生成：最大件数",
    "monthly_budget_jpy": "月のアプリ予算(円)", "ai_runs_per_code_per_month": "AI生成：1コードあたり月の回数",
    "ai_runs_global_per_month": "AI生成：全体の月の回数", "transcribe_minutes_per_code_per_month": "文字起こし：1コードあたり月の分数",
    "transcribe_minutes_global_per_month": "文字起こし：全体の月の分数", "usd_jpy": "為替（円/USD・見積用）",
    "model": "AIモデル", "input_usd_per_mtok": "入力料金(USD/100万トークン)", "output_usd_per_mtok": "出力料金(USD/100万トークン)",
    "transcribe_jpy_per_minute": "文字起こし単価(円/分)", "usage_store_persistent": "永続的な利用記録の保存先あり",
    "usage_ledger_path": "利用記録ファイル",
}


def render():
    s = state.settings()
    page_title("設定・利用枠", "上限・予算は環境変数（RP_ で始まる名前）または Streamlit の secrets で変更します。月予算を画面から増やすことはできません。")
    section("AIパスワード"); st.caption("AI生成の回数枠に使います。共有したコードは利用枠も共有されます")
    code = st.text_input("AIパスワード", type="password", value=st.session_state.get("access_code", ""),
                         help="平文では記録せず、ハッシュ値で回数を数えます。")
    st.session_state.access_code = code  # 画面を移動しても保持する
    blockers = paid_ai_blockers(s, st.session_state.get("access_code", ""))
    if blockers:
        st.warning("有料のAI処理は現在使えません：\n" + "\n".join(f"- {b}" for b in blockers))
        st.caption("デモ・手動入力・AIを使わない検索・Excel/JSON出力・ローカル文字起こしは使えます。")
    else:
        st.success(f"有料のAI処理を使えます（{s.budget.model}）。実行前に費用見込みを表示します。")
    lg = state.ledger()
    if lg:
        summ = lg.summary(st.session_state.get("access_code", ""))
        c = st.columns(4)
        c[0].metric("今月のAI生成（このコード）", f"{summ['code']['ai_runs']}/{s.budget.ai_runs_per_code_per_month}回")
        c[1].metric("今月のAI生成（全体）", f"{summ['all']['ai_runs']}/{s.budget.ai_runs_global_per_month}回")
        c[2].metric("今月の費用（見積・実績）", f"{summ['all']['cost_jpy']:,.0f}/{s.budget.monthly_budget_jpy:,}円")
        c[3].metric("内部API呼び出し", f"{summ['all']['api_calls']}回", help="画面上の実行回数とは別に数えています。")
        st.caption("アプリ予算は請求額の保証ではありません。Anthropic 側の利用上限（コンソールの支出上限）も併せて設定してください。")
    ok, why = local_whisper_available()
    st.markdown("**文字起こし**：" + (f"ローカル処理（faster-whisper・モデル {s.whisper_model}）が使えます。" if ok else why))
    st.markdown("**APIキー**：" + ("設定されています（値は表示しません）" if get_api_key() else "未設定"))
    rows = [{"項目": LABELS.get(k, k), "値": str(v), "環境変数名": "RP_" + k.upper()} for k, v in
            {**asdict(s.limits), **asdict(s.budget)}.items()]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
