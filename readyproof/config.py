"""設定値（上限・予算・料金）。

すべて環境変数または Streamlit secrets で上書きできる。
初期値の根拠は docs/design.md「容量と上限」を参照。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict

APP_NAME_EN = "ReadyProof AI"
APP_NAME_JA = "AI受入テスト・導入確認支援システム"
TAGLINE = "「うちの会社で使える？」に答えるAI"
DESCRIPTION = (
    "ベンダーの製品資料や営業説明の録画と、自社の業務ルール・作業手順を照合し、"
    "そのまま使える見込み、設定が必要な部分、追加対応が必要な部分、確認が必要な点を根拠付きで整理します。"
    "さらに、ベンダーへの質問、改修・設定変更依頼書、受入テストの作成と結果管理まで支援します。"
)
SCHEMA_VERSION = "1.0"


def _get(name: str, default):
    """環境変数 → secrets → 既定値 の順で取得し、既定値の型に合わせる。"""
    raw = os.environ.get(name)
    if raw is None:
        try:  # Streamlit 実行時のみ secrets を参照
            import streamlit as st

            if name in st.secrets:
                raw = st.secrets[name]
        except Exception:
            raw = None
    if raw is None:
        return default
    try:
        if isinstance(default, bool):
            return str(raw).strip().lower() in ("1", "true", "yes", "on")
        if isinstance(default, int):
            return int(raw)
        if isinstance(default, float):
            return float(raw)
        return str(raw)
    except (TypeError, ValueError):
        return default


@dataclass
class Limits:
    # 資料
    max_files_per_upload: int = 5
    max_file_mb: int = 20
    max_unzipped_mb: int = 100  # .docx/.xlsx/.pptx は ZIP。展開後サイズの上限（ZIP爆弾対策）
    max_chars_per_source: int = 200_000
    max_slides: int = 150
    max_pdf_pages: int = 300
    max_xlsx_rows_per_sheet: int = 3_000
    # 録画
    max_media_mb: int = 200
    max_media_minutes: int = 90
    max_transcribe_minutes_per_run: int = 15
    # AI
    max_ai_input_chars: int = 60_000
    max_ai_output_tokens: int = 16_000
    max_requirements_per_diagnosis: int = 10
    max_tests_per_generation: int = 15
    max_requests_per_generation: int = 1


@dataclass
class Budget:
    monthly_budget_jpy: int = 6_000  # 利用者の決定（2026-11-04）：月6,000円
    ai_runs_per_code_per_month: int = 3
    ai_runs_global_per_month: int = 60
    transcribe_minutes_per_code_per_month: int = 30
    transcribe_minutes_global_per_month: int = 300
    usd_jpy: float = 155.0
    # Claude 料金（USD / 100万トークン）。公式価格表で要確認（docs/design.md 参照）
    model: str = "claude-opus-5-5"
    input_usd_per_mtok: float = 4.0
    output_usd_per_mtok: float = 20.0
    # 文字起こし：ローカル処理は API 料金 0 円（計算資源は別）。外部API採用時はここに単価を設定
    transcribe_jpy_per_minute: float = 0.0
    # 永続的な利用記録の保存先が確保されていると運用者が明示した場合のみ有料処理を許可
    usage_store_persistent: bool = False
    usage_ledger_path: str = "data/usage_ledger.jsonl"


@dataclass
class Settings:
    limits: Limits = field(default_factory=Limits)
    budget: Budget = field(default_factory=Budget)
    whisper_model: str = "small"

    def as_dict(self) -> dict:
        return asdict(self)


def load_settings() -> Settings:
    lim = Limits()
    for k, v in asdict(lim).items():
        setattr(lim, k, _get("RP_" + k.upper(), v))
    bud = Budget()
    for k, v in asdict(bud).items():
        setattr(bud, k, _get("RP_" + k.upper(), v))
    return Settings(limits=lim, budget=bud, whisper_model=_get("RP_WHISPER_MODEL", "small"))
