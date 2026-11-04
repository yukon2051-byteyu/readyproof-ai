"""画面共通のデザイン（色・状態ラベル・CSS）。

方針（docs/design_research.md）：
- 作業画面は情報密度を優先し、装飾を抑える
- 状態は「色＋文字」で示す（色だけに頼らない）。枠線の実線／破線で人の確認済み／AI下書きを区別
- Streamlit の内部クラス名には依存せず、自前クラスと st.container(key=...) の st-key-* だけを使う
- アイコンは Streamlit の Material アイコン（:material/...:）を使い、絵文字・記号フォントに頼らない
"""
from __future__ import annotations

import html

import streamlit as st

# 文字色と背景色のコントラストは 4.5:1 以上になる組み合わせ（WCAG AA）
TONES = {
    "ok": ("#1E5631", "#E3F2E7"),
    "teal": ("#0B5563", "#E0F2F4"),
    "warn": ("#7A4B00", "#FFF1D6"),
    "bad": ("#8A1C1C", "#FBE4E4"),
    "info": ("#33465C", "#EAEFF5"),
    "purple": ("#5B2A86", "#F1E6FB"),
    "muted": ("#4A5563", "#F1F3F6"),
}

CATEGORY_TONE = {
    "そのまま対応できる見込み": "ok",
    "標準設定で対応できる見込み": "teal",
    "追加対応の検討が必要": "warn",
    "対応不可との記載・確認済み発言あり": "bad",
    "情報不足・ベンダー確認が必要": "info",
    "根拠間に矛盾あり": "purple",
}
RESULT_TONE = {"合格": "ok", "不合格": "bad", "未判定": "muted", "実施不能": "warn", "未実施": "muted", "実施中": "info"}
REQUEST_TONE = {"下書き": "muted", "確定": "info", "送付済み": "info", "回答待ち": "warn", "対応検討中": "warn",
                "対応中": "warn", "テスト待ち": "teal", "完了": "ok", "見送り": "muted"}

CSS = """
<style>
.rp-chip{display:inline-block;padding:1px 8px;margin:0 4px 2px 0;border-radius:4px;font-size:0.82rem;
  line-height:1.5;border:1px solid currentColor;white-space:nowrap;font-weight:600}
.rp-chip.draft{border-style:dashed;font-weight:500}
.rp-ctx{display:flex;flex-wrap:wrap;gap:6px 18px;align-items:center;padding:6px 12px;margin:-8px 0 10px 0;
  background:#F3F6FA;border:1px solid #D5DDE8;border-radius:6px;font-size:0.88rem;color:#1A2433}
.rp-ctx b{color:#1F3A5F}
.rp-steps{display:flex;flex-wrap:wrap;gap:4px;margin:0}
.rp-step{padding:1px 8px;border-radius:12px;font-size:0.8rem;border:1px solid #B7C2D0;color:#33465C;background:#fff}
.rp-step.on{background:#1F3A5F;color:#fff;border-color:#1F3A5F}
.rp-quote{border-left:3px solid #8DA2BC;padding:2px 10px;margin:4px 0;color:#1A2433;background:#F8FAFC;
  white-space:pre-wrap;word-break:break-word}
.rp-small{font-size:0.85rem;color:#4A5563}
.rp-hero h1{font-size:2.1rem;margin:0 0 2px 0;color:#1F3A5F}
.rp-hero .ja{font-size:1.05rem;color:#33465C;margin:0 0 14px 0}
.rp-hero .tag{font-size:1.45rem;font-weight:700;color:#1A2433;margin:0 0 8px 0;line-height:1.5}
.rp-flow{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin:6px 0}
.rp-flow div{border:1px solid #D5DDE8;border-radius:6px;padding:8px 10px;background:#fff;font-size:0.88rem}
.rp-flow div b{display:block;color:#1F3A5F;margin-bottom:2px}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def esc(text) -> str:
    """HTML 表示前のエスケープ（資料や発言に含まれるタグを無効化）。"""
    return html.escape(str(text if text is not None else ""))


def chip(label: str, tone: str = "muted", draft: bool = False) -> str:
    fg, bg = TONES.get(tone, TONES["muted"])
    cls = "rp-chip draft" if draft else "rp-chip"
    return f'<span class="{cls}" style="color:{fg};background:{bg}">{esc(label)}</span>'


def category_chip(cat: str | None) -> str:
    if not cat:
        return chip("診断なし", "muted")
    return chip(cat, CATEGORY_TONE.get(cat, "muted"))


def review_chip(status: str, origin: str = "") -> str:
    if status == "人が確認済み":
        return chip("人が確認済み", "ok")
    if status == "要修正":
        return chip("要修正", "warn", draft=True)
    label = {"準備済みのデモ結果": "準備済みのデモ結果（未確認）", "AI生成": "AI下書き（未確認）"}.get(origin, "手動作成（未確認）")
    return chip(label, "muted", draft=True)


def html_line(*parts: str) -> None:
    st.markdown(" ".join(parts), unsafe_allow_html=True)


def quote(text: str) -> None:
    st.markdown(f'<div class="rp-quote">{esc(text)}</div>', unsafe_allow_html=True)
