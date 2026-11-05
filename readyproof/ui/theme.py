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
GOLD = "#E0B84A"       # 金の差し色（出力・人の判断・実機の結果など、位置づけが違うものの区別に使う）
GOLD_TEXT = "#8A6500"  # 白地に置く金色の文字（読みやすさのため濃くする）
JUDGE = "#2F9E6E"  # 判断（人が決める工程）の色
JUDGE_TEXT = "#1E7B45"
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
    "情報不足・ベンダー確認が必要": ("orange", "help"),
    "根拠間に矛盾あり": ("orange", "sync_problem"),
}
CATEGORY_TONE = {k: {"green": "ok", "orange": "warn", "red": "bad", "gray": "muted", "violet": "purple"}[v[0]]
                 for k, v in CATEGORY_STYLE.items()}
RESULT_TONE = {"合格": "ok", "不合格": "bad", "未判定": "muted", "実施不能": "warn", "未実施": "muted", "実施中": "active"}
REQUEST_TONE = {"下書き": "muted", "確定": "muted", "送付済み": "active", "回答待ち": "active", "対応検討中": "active",
                "対応中": "active", "テスト待ち": "active", "完了": "ok", "見送り": "muted"}

CSS = f"""
<style>
/* 上の余白を詰める（Streamlit 標準は約6rem） */
[data-testid="stMainBlockContainer"] {{ padding-top: 1.4px; padding-bottom: 3rem; max-width: 1240px; }}
[data-testid="stHeader"] {{ background: transparent; height: 2.5rem; }}

/* 背景（薄い灰色）と枠の中（白）を分ける */
[data-testid="stApp"] {{ background: {PAGE_BG}; }}
[data-testid="stSidebar"] {{ background: #FFFFFF; border-right: 1px solid {BORDER}; }}
div[class*="st-key-rpbox_"], [data-testid="stForm"], [data-testid="stExpander"] details {{
  background: #FFFFFF; border-color: {BORDER} !important; box-shadow: 0 1px 2px rgba(20, 38, 63, .06); }}
div[class*="st-key-rpbox_"] {{ padding: 14px 18px; }}

/* 画面の見出し（3段階：画面名 1.55rem／小見出し 1.05rem／本文） */
.rp-ctx {{ font-size: .82rem; color: {MUTED}; margin: 0 0 .1rem; }}
.rp-title {{ font-size: 1.55rem; font-weight: 700; color: {NAVY}; line-height: 1.35; margin: 0; }}
.rp-desc {{ font-size: .9rem; color: {MUTED}; margin: .15rem 0 1rem; }}
.rp-h {{ font-size: 1.05rem; font-weight: 700; color: {NAVY}; margin: 1.3rem 0 .5rem; padding-left: 10px;
  border-left: 4px solid {ACCENT}; line-height: 1.3; }}
.rp-h.big {{ font-size: 1.4rem; font-weight: 800; }}
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
.rp-card.role {{ background: #FBF3DC; border-color: #EBD9A6; border-top-color: #E0B84A; }}
.rp-card.role .t {{ font-size: .98rem; }}
.rp-card ul {{ margin: 0 0 0 1.1rem; padding: 0; font-size: .86rem; color: #1F2937; }}

/* トップページの見出し帯（紺のグラデーション＋右側に「根拠を確かめる書類」のモチーフ） */
.rp-hero {{ position: relative; overflow: hidden; border-radius: 14px; padding: 28px 32px 26px; margin: 0 0 18px;
  background: linear-gradient(120deg, {NAVY} 0%, #1B3A63 55%, #1F4E8C 100%); }}
.rp-hero .motif {{ position: absolute; right: 22px; top: 14px; width: 150px; height: 150px;
  opacity: .9; pointer-events: none; }}
.rp-hero .inner {{ position: relative; max-width: 78%; }}
.rp-hero .eyebrow {{ display: inline-block; font-size: .82rem; color: {NAVY}; background: {ACCENT}; font-weight: 700;
  padding: 2px 10px; border-radius: 999px; letter-spacing: .03em; }}
.rp-hero .name {{ font-size: 2.7rem; font-weight: 800; color: #fff; line-height: 1.15; margin: 10px 0 10px; }}
.rp-hero .name span {{ color: {ACCENT}; }}
.rp-hero .tag {{ font-size: 1.3rem; font-weight: 700; color: #fff; line-height: 1.5; }}
.rp-hero .tag em {{ font-style: normal; color: {ACCENT}; }}
.rp-hero .desc {{ font-size: .95rem; color: #E0B84A; font-weight: 500; margin-top: 10px; }}
@media (min-width: 1100px) {{ .rp-hero .desc {{ white-space: nowrap; }} .rp-hero .inner {{ max-width: 100%; }}
  .rp-hero .tag, .rp-hero .name, .rp-hero .eyebrow {{ max-width: 76%; }} }}

/* トップ：3分デモの流れと成果物の見本（左右の高さをそろえ、下のボタンの位置を合わせる） */
.rp-flow {{ display: flex; flex-direction: column; gap: 8px; height: 340px; margin-bottom: 12px; }}
.rp-flow .st {{ flex: 1; display: flex; gap: 12px; align-items: center; background: #fff; border: 1px solid {BORDER};
  border-radius: 8px; padding: 6px 12px; box-shadow: 0 1px 2px rgba(20, 38, 63, .06); line-height: 1.35; }}
.rp-result {{ height: 340px; box-sizing: border-box; display: flex; flex-direction: column; background: #fff;
  border: 1px solid {BORDER}; border-top: 3px solid {ACCENT}; border-radius: 10px; padding: 12px 16px; margin-bottom: 12px;
  box-shadow: 0 1px 3px rgba(20, 38, 63, .08); }}
.rp-result .h {{ font-weight: 700; color: {NAVY}; margin-bottom: 4px; }}
.rp-result .row {{ display: grid; grid-template-columns: 6.2em 1fr; gap: 8px; padding: 6px 0; border-bottom: 1px dashed #E5EAF0;
  font-size: .88rem; line-height: 1.5; }}
.rp-result .lb {{ color: {MUTED}; font-size: .8rem; }}
.rp-result .q {{ display: inline-block; margin-top: 3px; background: #EAF7FE; border-left: 3px solid {ACCENT}; padding: 1px 8px; }}
.rp-result .ok {{ color: #1E7B45; }} .rp-result .ng {{ color: #B42318; }}
.rp-result .foot {{ font-size: .8rem; color: {MUTED}; margin-top: auto; padding-top: 6px; }}

/* 根拠の原文（前後の行と、引用部分の印） */
.rp-ctxbox {{ border: 1px solid #E5EAF0; border-radius: 8px; overflow: hidden; margin: 4px 0 8px; }}
.rp-ctxrow {{ display: grid; grid-template-columns: 11em 1fr; gap: 10px; padding: 5px 10px; font-size: .86rem;
  border-top: 1px solid #F0F3F7; color: #4B5563; }}
.rp-ctxrow:first-child {{ border-top: none; }}
.rp-ctxrow .loc {{ font-size: .76rem; color: {MUTED}; }}
.rp-ctxrow.hit {{ background: #F3FAFF; border-left: 4px solid {ACCENT}; color: #1F2937; }}
mark.rp-mark {{ background: #BFE9FC; color: inherit; padding: 0 2px; border-radius: 3px; }}

/* 4段階の進み具合（①製品の資料 → ②自社のルール → ③診断結果 → ④受入テスト） */
.rp-stepper {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; margin: 4px 0 14px; }}
.rp-step {{ display: flex; gap: 10px; align-items: center; background: #fff; border: 1px solid {BORDER}; border-radius: 10px;
  padding: 9px 12px; box-shadow: 0 1px 2px rgba(20, 38, 63, .06); }}
.rp-step .no {{ flex: none; width: 30px; height: 30px; border-radius: 50%; display: inline-flex; align-items: center;
  justify-content: center; font-weight: 800; background: #E5EAF0; color: {MUTED}; }}
.rp-step .io {{ font-size: .72rem; color: {MUTED}; letter-spacing: .04em; }}
.rp-step .nm {{ font-size: .98rem; font-weight: 700; color: {NAVY}; line-height: 1.3; }}
.rp-step .sb {{ font-size: .76rem; color: {MUTED}; }}
.rp-step.done {{ border-bottom: 3px solid {ACCENT}; }}
.rp-step.done .no {{ background: {ACCENT}; color: {NAVY}; }}
.rp-step.cur {{ background: {NAVY}; border-color: {NAVY}; }}
.rp-step.cur .no {{ background: {ACCENT}; color: {NAVY}; }}
.rp-step.cur .io, .rp-step.cur .sb {{ color: #B9C7DA; }}
.rp-step.cur .nm {{ color: #fff; }}

/* 金の差し色：入力と出力、見込みと実機結果など、位置づけの違うものを並べたときに使う */
.rp-h.gold {{ border-left-color: {GOLD}; }}
.rp-card.out {{ border-top-color: {GOLD}; }}
.rp-card.out .rp-num, .rp-num.gold {{ color: {GOLD}; }}
.rp-card.out .m {{ color: {GOLD_TEXT}; font-weight: 700; }}
.rp-card .m.in {{ color: #1F6F99; font-weight: 700; }}
.rp-step.out.done {{ border-bottom-color: {GOLD}; }}
.rp-step.out.done .no, .rp-step.out.cur .no {{ background: {GOLD}; color: {NAVY}; }}
.rp-step.out .io {{ color: {GOLD_TEXT}; }}
.rp-step.out.cur .io {{ color: {GOLD}; }}
.rp-step.judge.done {{ border-bottom-color: {JUDGE}; }}
.rp-step.judge.done .no, .rp-step.judge.cur .no {{ background: {JUDGE}; color: #fff; }}
.rp-step.judge .io {{ color: {JUDGE_TEXT}; }}
.rp-step.judge.cur .io {{ color: #7FD3AE; }}
.rp-cond3 {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); margin: 4px 0 12px; }}
.rp-cond3 > div {{ padding: 0 18px; }}
.rp-cond3 > div:first-child {{ padding-left: 0; }}
.rp-cond3 > div + div {{ border-left: 1px solid {BORDER}; }}
.rp-cond3 .h {{ font-weight: 700; color: {NAVY}; margin-bottom: 6px; }}
.rp-cond3 ul {{ margin: 0; padding-left: 1.1rem; }}
.rp-cond3 li {{ margin-bottom: 4px; line-height: 1.6; }}
@media (max-width: 800px) {{ .rp-cond3 {{ grid-template-columns: 1fr; }} .rp-cond3 > div {{ padding: 8px 0; }}
  .rp-cond3 > div + div {{ border-left: none; border-top: 1px solid {BORDER}; }} }}
/* ③ 診断結果：第1階層（診断サマリー） */
.rp-h.md {{ font-size: 1.2rem; }}
.rp-sum {{ background: #fff; border: 1px solid {BORDER}; border-left: 5px solid {NAVY}; border-radius: 10px; padding: 16px 20px; margin: 2px 0 14px; }}
.rp-sum .meta {{ display: flex; flex-wrap: wrap; gap: 6px 12px; justify-content: space-between; align-items: center; font-size: .85rem; color: {MUTED}; }}
.rp-sum .st {{ font-size: .85rem; font-weight: 700; padding: 2px 10px; border-radius: 999px; background: #EEF1F5; color: #3F4A5A; }}
.rp-sum .st.warn {{ background: #FDF1DF; color: #8A4B08; }}
.rp-sum .st.ok {{ background: #E5F4EB; color: #1E7B45; }}
.rp-sum .head {{ font-size: 1.5rem; font-weight: 800; color: {NAVY}; line-height: 1.4; margin: 8px 0 6px; }}
.rp-sum .sub {{ font-size: 1rem; color: #374151; line-height: 1.7; max-width: 60em; }}
.rp-points {{ margin: 0 0 6px; padding: 0; list-style: none; font-size: .95rem; line-height: 1.7; }}
.rp-body {{ font-size: .95rem; line-height: 1.7; max-width: 62em; margin: 6px 0; color: #1F2937; }}
.rp-tbl {{ border-collapse: collapse; font-size: .92rem; }}
.rp-tbl td {{ padding: 3px 18px 3px 0; border: none; }}
.rp-tbl td.n {{ text-align: right; font-weight: 700; }}
.rp-act {{ display: flex; gap: 10px; align-items: flex-start; }}
.rp-act .no {{ flex: none; width: 26px; height: 26px; border-radius: 50%; background: {NAVY}; color: #fff; font-size: .85rem; font-weight: 700;
  display: inline-flex; align-items: center; justify-content: center; margin-top: 1px; }}
.rp-act .t {{ font-size: 1rem; font-weight: 700; color: {NAVY}; line-height: 1.5; }}
.rp-act .s {{ font-size: .76rem; font-weight: 500; color: #8A4B08; background: #FDF1DF; border-radius: 4px; padding: 1px 6px; margin-left: 8px; }}
.rp-act .d {{ font-size: .86rem; color: {MUTED}; line-height: 1.55; }}
/* ③ 診断結果：第2階層（要件カード） */
.rp-rq .hd {{ display: flex; flex-wrap: wrap; gap: 2px 10px; align-items: baseline; }}
.rp-rq .t {{ font-size: 1.08rem; font-weight: 700; color: {NAVY}; line-height: 1.45; }}
.rp-rq .id {{ font-size: .76rem; color: {MUTED}; }}
.rp-rq .pl {{ margin: 6px 0; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }}
.rp-rq .prio {{ font-size: .78rem; color: #3F4A5A; background: #EEF1F5; border-radius: 4px; padding: 1px 6px; }}
.rp-rq .why {{ font-size: .95rem; line-height: 1.65; color: #1F2937; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
.rp-rq .nd {{ font-size: .95rem; font-weight: 600; color: {NAVY}; margin-top: 6px; }}
.rp-rq .nd .lb {{ font-size: .78rem; font-weight: 500; color: {MUTED}; margin-right: 8px; }}
.rp-rq .ck {{ display: flex; flex-wrap: wrap; gap: 4px 12px; margin: 8px 0 10px; }}
.rp-pill {{ display: inline-block; font-size: .88rem; font-weight: 700; padding: 2px 10px; border-radius: 6px; border: 1px solid transparent; }}
.rp-pill.likely {{ background: #F0F9F3; color: #1E7B45; border: 1px dashed #5FAF80; }}
.rp-pill.extra, .rp-pill.check {{ background: #FDF1DF; color: #8A4B08; border-color: #F0CF9A; }}
.rp-pill.hard {{ background: #FCE9E7; color: #B42318; border-color: #F2B8B1; }}
.rp-pill.none {{ background: #EEF1F5; color: #3F4A5A; border-color: #D5DBE3; }}
.rp-ck {{ font-size: .78rem; color: {MUTED}; white-space: nowrap; }}
.rp-ck.ok {{ color: #1E7B45; }} .rp-ck.wait {{ color: #8A4B08; }} .rp-ck.bad {{ color: #B42318; font-weight: 700; }}
/* ③ 診断結果：第3階層（詳細） */
.rp-reqtext {{ font-size: .95rem; line-height: 1.65; border-left: 3px solid #C9D3E0; background: #F7F9FC; padding: 6px 12px; margin-bottom: 8px; }}
.rp-reqtext .lb {{ display: block; font-size: .76rem; color: {MUTED}; }}
div[data-testid="stButtonGroup"] > div {{ flex-wrap: wrap; }}
@media (max-width: 768px) {{ [data-testid="stMainBlockContainer"] {{ padding-top: 3.2rem; }} [data-testid="stHeader"] {{ background: {PAGE_BG}; }} }}
@media (max-width: 640px) {{ .rp-sum {{ padding: 12px 14px; }} .rp-sum .head {{ font-size: 1.3rem; }} .rp-ck {{ white-space: normal; }} }}
/* 画面移動時に最上部へ戻すための見えない部品（高さ0）が、すき間を作らないようにする */
div[data-testid="stElementContainer"]:has(> iframe[data-testid="stIFrame"]) {{ position: absolute; height: 0; margin: 0; overflow: hidden; }}
.rp-tile.gold {{ border-top: 4px solid {GOLD}; }}

/* 一覧の1行カード（左：内容、右：ボタン） */
.rp-item .h {{ font-weight: 700; color: {NAVY}; }}
.rp-item .s {{ font-size: .84rem; color: {MUTED}; }}

/* ガイド付きデモの帯 */
.st-key-tour {{ background: #FFFFFF; border: 1px solid {BORDER}; border-left: 5px solid {ACCENT}; border-radius: 10px;
  padding: 10px 14px 8px; margin-bottom: 6px; box-shadow: 0 1px 3px rgba(20, 38, 63, .08); }}

@media (max-width: 800px) {{ .rp-stepper {{ grid-template-columns: 1fr 1fr; }} .rp-flow, .rp-result {{ height: auto; }} .rp-ctxrow {{ grid-template-columns: 1fr; }} .rp-grid {{ grid-template-columns: 1fr; }} .rp-hero .name {{ font-size: 2rem; }}
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
    label = ("AIの下書き・未確認" if (origin or "").startswith("AI生成")
             else {"準備済みのデモ結果": "準備済みのデモ結果・未確認"}.get(origin, "手動作成・未確認"))
    return badge(label, "gray", "edit_note")


PILL_MARK = {"likely": "○", "extra": "△", "hard": "×", "check": "？", "none": "－"}
CHECK_MARK = {"ok": "✓", "wait": "…", "bad": "！", "none": "－"}


def status_pill(label: str, group: str) -> str:
    """診断結果の札。色だけに頼らず印と文字でも示す。「見込み」は破線にして、確定した成功に見せない。"""
    return f"<span class='rp-pill {esc(group)}'>{PILL_MARK.get(group, '')} {esc(label)}</span>"


def check_chip(name: str, text: str, state: str) -> str:
    """確認状態（AI診断・人の確認・ベンダー回答・実機テストを別々に示す）。"""
    return f"<span class='rp-ck {esc(state)}'>{CHECK_MARK.get(state, '')} {esc(name)}：{esc(text)}</span>"


def meta(text: str) -> str:
    """補足情報（色を付けない灰色の小さな文字）。"""
    return f'<span class="rp-small">{esc(text)}</span>'


def html_line(*parts: str) -> None:
    st.markdown(" ".join(parts), unsafe_allow_html=True)


def quote(text: str) -> None:
    st.markdown(f'<div class="rp-quote">{esc(text)}</div>', unsafe_allow_html=True)


def section(title: str, top: str | None = None, gold: bool = False, big: bool = False, size: str = "") -> None:
    """小見出し。top で上の余白を個別に調整（例："-7px"）。gold=True で縦線を金色、big=True で文字を大きく、size="md" で中くらいに。"""
    style = f' style="margin-top:{top}"' if top else ""
    cls = "rp-h" + (" gold" if gold else "") + (" big" if big else "") + (f" {size}" if size else "")
    st.markdown(f'<div class="{cls}"{style}>{esc(title)}</div>', unsafe_allow_html=True)


def tiles(items: list[dict], cols: int | None = None) -> None:
    """数値の枠を横に並べる（高さをそろえる）。items: {label, value, note?, alert?, color?（上の線の色）}"""
    n = cols or len(items)
    parts = []
    for it in items:
        cls = "rp-tile alert" if it.get("alert") else ("rp-tile gold" if it.get("gold") else "rp-tile")
        style = f' style="border-top:4px solid {it["color"]}"' if it.get("color") else ""
        parts.append(f'<div class="{cls}"{style}><div class="lb">{esc(it["label"])}</div>'
                     f'<div class="v">{esc(it["value"])}</div><div class="n">{esc(it.get("note", "")) or "&nbsp;"}</div></div>')
    st.markdown(f'<div class="rp-grid" style="--cols:{n}">{"".join(parts)}</div>', unsafe_allow_html=True)
