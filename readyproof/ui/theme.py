"""画面共通のデザイン（色・状態ラベル・余白・枠）。

方針（docs/design_research.md）：
- 色は役割を固定して数を絞る。紺＝ブランド・主操作、緑＝OK・見込みあり、橙＝注意・追加対応、
  赤＝不可・不合格、紫＝矛盾、灰＝未確認・不明・補足情報、青＝進行中だけ
- 状態は Streamlit 標準の「バッジ」（:color-badge[...]）で、色＋文字（＋アイコン）で示す
- 補足情報（作成元・種類など）は色を付けず、灰色の小さな文字にする
- 文字サイズは「画面名／小見出し／本文」の3段階
- 横に並ぶ枠は CSS グリッドで高さをそろえる（下端をそろえる）
- Streamlit 内部のクラス名には依存しない。data-testid と st.container(key=...) の st-key-* のみ使う
"""
from __future__ import annotations

import html

import streamlit as st

NAVY = "#14263F"
ACCENT = "#38BDF8"  # ブランドの差し色（明るい空色）。見出し帯・見出しの縦線・番号に使う
PAGE_BG = "#EEF2F7"
PRIMARY = "#1F4E8C"
MUTED = "#5B6574"
BORDER = "#DDE3EA"

# 状態の種類 → Streamlit バッジの色
TONE_COLOR = {"ok": "green", "teal": "green", "warn": "orange", "bad": "red", "purple": "violet",
              "active": "blue", "info": "gray", "muted": "gray"}

CATEGORY_STYLE = {
    "そのまま対応できる見込み": ("green", "check_circle"),
    "標準設定で対応できる見込み": ("green", "tune"),
    "追加対応の検討が必要": ("orange", "build"),
    "対応不可との記載・確認済み発言あり": ("red", "block"),
    "情報不足・ベンダー確認が必要": ("gray", "help"),
    "根拠間に矛盾あり": ("violet", "sync_problem"),
}
CATEGORY_TONE = {k: {"green": "ok", "orange": "warn", "red": "bad", "gray": "muted", "violet": "purple"}[v[0]]
                 for k, v in CATEGORY_STYLE.items()}
RESULT_TONE = {"合格": "ok", "不合格": "bad", "未判定": "muted", "実施不能": "warn", "未実施": "muted", "実施中": "active"}
REQUEST_TONE = {"下書き": "muted", "確定": "muted", "送付済み": "active", "回答待ち": "active", "対応検討中": "active",
                "対応中": "active", "テスト待ち": "active", "完了": "ok", "見送り": "muted"}

CSS = f"""
<style>
/* 上の余白を詰める（Streamlit 標準は約6rem） */
[data-testid="stMainBlockContainer"] {{ padding-top: 1.75rem; padding-bottom: 3rem; max-width: 1240px; }}
[data-testid="stHeader"] {{ background: transparent; height: 2.5rem; }}

/* 背景（薄い灰色）と枠の中（白）を分ける */
[data-testid="stApp"] {{ background: {PAGE_BG}; }}
[data-testid="stSidebar"] {{ background: #FFFFFF; border-right: 1px solid {BORDER}; }}
div[class*="st-key-rpbox_"], [data-testid="stForm"], [data-testid="stExpander"] details {{
  background: #FFFFFF; border-color: {BORDER} !important; box-shadow: 0 1px 2px rgba(20, 38, 63, .06); }}
div[class*="st-key-rpbox_"] {{ padding: 2px 4px; }}

/* 画面の見出し（3段階：画面名 1.55rem／小見出し 1.05rem／本文） */
.rp-ctx {{ font-size: .82rem; color: {MUTED}; margin: 0 0 .1rem; }}
.rp-title {{ font-size: 1.55rem; font-weight: 700; color: {NAVY}; line-height: 1.35; margin: 0; }}
.rp-desc {{ font-size: .9rem; color: {MUTED}; margin: .15rem 0 1rem; }}
.rp-h {{ font-size: 1.05rem; font-weight: 700; color: {NAVY}; margin: 1.3rem 0 .5rem; padding-left: 10px;
  border-left: 4px solid {ACCENT}; line-height: 1.3; }}
.rp-small {{ font-size: .84rem; color: {MUTED}; }}
.rp-quote {{ border-left: 3px solid #C9D3E0; background: #F7F9FC; padding: 4px 10px; margin: 4px 0 8px;
  white-space: pre-wrap; word-break: break-word; }}

/* 横並びの枠：高さをそろえる */
.rp-grid {{ display: grid; grid-template-columns: repeat(var(--cols), minmax(0, 1fr)); gap: 12px;
  align-items: stretch; margin: .2rem 0 1rem; }}
.rp-tile {{ border: 1px solid {BORDER}; border-radius: 8px; padding: 12px 14px; background: #fff;
  box-shadow: 0 1px 2px rgba(20, 38, 63, .06);
  display: flex; flex-direction: column; }}
.rp-tile .lb {{ font-size: .82rem; color: {MUTED}; min-height: 2.6em; }}
.rp-tile .v {{ font-size: 1.55rem; font-weight: 700; color: {NAVY}; line-height: 1.25; padding-top: 4px; }}
.rp-tile .n {{ font-size: .76rem; color: {MUTED}; margin-top: auto; padding-top: 4px; }}
.rp-tile.alert {{ border-color: #E9B4B4; }}
.rp-tile.alert .v {{ color: #B42318; }}
.rp-card {{ border: 1px solid {BORDER}; border-radius: 10px; padding: 16px 18px; background: #fff;
  box-shadow: 0 1px 3px rgba(20, 38, 63, .08); border-top: 3px solid {ACCENT};
  display: flex; flex-direction: column; gap: 6px; }}
.rp-card .t {{ font-size: 1.05rem; font-weight: 700; color: {NAVY}; display: flex; align-items: center; gap: 8px; }}
.rp-num {{ display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px; border-radius: 50%;
  background: {NAVY}; color: {ACCENT}; font-size: .85rem; font-weight: 800; flex: none; }}
.rp-card .b {{ font-size: .9rem; color: #1F2937; }}
.rp-card .m {{ font-size: .8rem; color: {MUTED}; margin-top: auto; padding-top: 6px; }}
.rp-card.role .t {{ font-size: .98rem; }}
.rp-card ul {{ margin: 0 0 0 1.1rem; padding: 0; font-size: .86rem; color: #1F2937; }}

/* トップページの見出し帯（紺のグラデーション＋右側に「根拠を確かめる書類」のモチーフ） */
.rp-hero {{ position: relative; overflow: hidden; border-radius: 14px; padding: 28px 32px 26px; margin: 0 0 18px;
  background: linear-gradient(120deg, {NAVY} 0%, #1B3A63 55%, #1F4E8C 100%); }}
.rp-hero .motif {{ position: absolute; right: 26px; top: 50%; transform: translateY(-50%); width: 190px; height: 190px;
  opacity: .9; pointer-events: none; }}
.rp-hero .inner {{ position: relative; max-width: 78%; }}
.rp-hero .eyebrow {{ display: inline-block; font-size: .82rem; color: {NAVY}; background: {ACCENT}; font-weight: 700;
  padding: 2px 10px; border-radius: 999px; letter-spacing: .03em; }}
.rp-hero .name {{ font-size: 2.7rem; font-weight: 800; color: #fff; line-height: 1.15; margin: 10px 0 10px; }}
.rp-hero .name span {{ color: {ACCENT}; }}
.rp-hero .tag {{ font-size: 1.3rem; font-weight: 700; color: #fff; line-height: 1.5; }}
.rp-hero .tag em {{ font-style: normal; color: {ACCENT}; }}
.rp-hero .desc {{ font-size: .95rem; color: #DCE4EE; margin-top: 6px; }}

/* ガイド付きデモの帯 */
.st-key-tour {{ background: #FFFFFF; border: 1px solid {BORDER}; border-left: 5px solid {ACCENT}; border-radius: 10px;
  padding: 10px 14px 8px; margin-bottom: 6px; box-shadow: 0 1px 3px rgba(20, 38, 63, .08); }}

@media (max-width: 800px) {{ .rp-grid {{ grid-template-columns: 1fr; }} .rp-hero .name {{ font-size: 2rem; }}
  .rp-hero .motif {{ display: none; }} .rp-hero .inner {{ max-width: 100%; }} }}
</style>
"""


def inject_css() -> None:
    st.session_state["_box_n"] = 0  # 枠の通し番号を実行ごとに振り直す
    st.markdown(CSS, unsafe_allow_html=True)


def box():
    """白い枠（背景の灰色と区別する）。st.container(border=True) の代わりに使う。"""
    n = st.session_state.get("_box_n", 0) + 1
    st.session_state["_box_n"] = n
    return st.container(border=True, key=f"rpbox_{n}")


def esc(text) -> str:
    """HTML 表示前のエスケープ（資料や発言に含まれるタグを無効化）。"""
    return html.escape(str(text if text is not None else ""))


def badge(label: str, color: str = "gray", icon: str | None = None) -> str:
    """Streamlit 標準のバッジ（Markdown 記法）。文字と色の両方で状態を示す。"""
    safe = esc(label).replace("[", "（").replace("]", "）")
    ic = f":material/{icon}: " if icon else ""
    return f":{color}-badge[{ic}{safe}] "


def chip(label: str, tone: str = "muted", draft: bool = False) -> str:
    return badge(label, TONE_COLOR.get(tone, "gray"))


def category_chip(cat: str | None) -> str:
    if not cat:
        return badge("診断なし", "gray")
    color, icon = CATEGORY_STYLE.get(cat, ("gray", None))
    return badge(cat, color, icon)


def review_chip(status: str, origin: str = "") -> str:
    if status == "人が確認済み":
        return badge("人が確認済み", "green", "verified")
    if status == "要修正":
        return badge("要修正", "orange", "edit")
    label = {"準備済みのデモ結果": "準備済みのデモ結果・未確認", "AI生成": "AIの下書き・未確認"}.get(origin, "手動作成・未確認")
    return badge(label, "gray", "edit_note")


def meta(text: str) -> str:
    """補足情報（色を付けない灰色の小さな文字）。"""
    return f'<span class="rp-small">{esc(text)}</span>'


def html_line(*parts: str) -> None:
    st.markdown(" ".join(parts), unsafe_allow_html=True)


def quote(text: str) -> None:
    st.markdown(f'<div class="rp-quote">{esc(text)}</div>', unsafe_allow_html=True)


def section(title: str) -> None:
    st.markdown(f'<div class="rp-h">{esc(title)}</div>', unsafe_allow_html=True)


def tiles(items: list[dict], cols: int | None = None) -> None:
    """数値の枠を横に並べる（高さをそろえる）。items: {label, value, note?, alert?}"""
    n = cols or len(items)
    html_ = "".join(
        f'<div class="rp-tile{" alert" if it.get("alert") else ""}"><div class="lb">{esc(it["label"])}</div>'
        f'<div class="v">{esc(it["value"])}</div><div class="n">{esc(it.get("note", "")) or "&nbsp;"}</div></div>'
        for it in items)
    st.markdown(f'<div class="rp-grid" style="--cols:{n}">{html_}</div>', unsafe_allow_html=True)
