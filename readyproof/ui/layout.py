"""4段階の画面の共通部品：進み具合（①〜④）・画面名・次へのボタン。"""
from __future__ import annotations

import streamlit as st

from ..core import primary_product
from ..logic.rules import current_diagnosis, latest_run
from . import state
from .components import tour_bar
from .theme import esc

STEPS = [
    ("input1", "製品の資料", "入力1"),
    ("input2", "自社のルール", "入力2"),
    ("result", "診断結果", "出力1"),
    ("tests", "受入テスト", "出力2"),
]


def _counts(p: dict) -> dict:
    srcs = [s for s in p["sources"] if s["owner"] == "製品"]
    reqs = [r for r in p["requirements"] if r["status"] != "廃止"]
    diag = sum(1 for r in reqs if current_diagnosis(p, r["id"]))
    tests = [t for t in p["tests"] if t["status"] != "廃止"]
    done = sum(1 for t in tests if (latest_run(p, t["id"]) or {}).get("status") == "完了")
    return {
        "input1": (len(srcs) + len(p["recordings"]), f"資料 {len(srcs)}件・録画 {len(p['recordings'])}件"),
        "input2": (len(reqs), f"要件 {len(reqs)}件（確定 {sum(1 for r in reqs if r['status'] == '確定')}）"),
        "result": (diag, f"診断 {diag}/{len(reqs)}件"),
        "tests": (len(tests), f"テスト {len(tests)}件（実施 {done}）"),
    }


def stepper(current: str) -> None:
    p = state.project()
    if not p:
        return
    c = _counts(p)
    items = []
    for i, (key, name, io) in enumerate(STEPS):
        n, sub = c[key]
        cls = "cur" if key == current else ("done" if n else "")
        items.append(f'<div class="rp-step {cls}"><span class="no">{i + 1}</span><div><div class="io">{esc(io)}</div>'
                     f'<div class="nm">{esc(name)}</div><div class="sb">{esc(sub)}</div></div></div>')
    prod = primary_product(p) or {}
    demo = "架空のデモ ／ " if p["project"].get("demo_id") else ""
    st.markdown(f'<div class="rp-ctx">{esc(demo)}{esc(p["project"]["name"])} ／ {esc(prod.get("name", "製品未登録"))}'
                f'（{esc(prod.get("plan") or "プラン未記入")}）</div>'
                f'<div class="rp-stepper">{"".join(items)}</div>', unsafe_allow_html=True)


def header(key: str, title: str, desc: str) -> dict | None:
    """画面の先頭：デモの案内（デモ中のみ）→ 進み具合 → 画面名と説明。案件がなければ案内して None。"""
    p = state.require_project()
    if not p:
        return None
    tour_bar(key)
    stepper(key)
    st.markdown(f'<div class="rp-title">{esc(title)}</div><div class="rp-desc">{esc(desc)}</div>',
                unsafe_allow_html=True)
    return p


def next_button(label: str, page_key: str) -> None:
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    _, c = st.columns([3, 1.4])
    if c.button(label, type="primary", icon=":material/arrow_forward:", width="stretch", key=f"next_{page_key}"):
        state.goto(page_key)
