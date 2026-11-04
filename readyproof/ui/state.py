"""画面の状態（利用者ごとのセッション）と共通操作。

st.session_state は閲覧者ごとに分かれるため、編集内容は他の利用者と混ざらない。
"""
from __future__ import annotations

import copy

import streamlit as st

from ..config import load_settings
from ..core import primary_product
from ..usage import Ledger

PAGES: dict = {}  # app.py で登録（key -> st.Page）


def settings():
    if "settings" not in st.session_state:
        st.session_state.settings = load_settings()
    return st.session_state.settings


def ledger() -> Ledger | None:
    s = settings()
    if not s.budget.usage_store_persistent:
        return None
    return Ledger(s.budget.usage_ledger_path)


def project() -> dict | None:
    return st.session_state.get("project")


def set_project(p: dict, demo_initial: dict | None = None) -> None:
    st.session_state.project = p
    st.session_state.demo_initial = copy.deepcopy(demo_initial) if demo_initial else None
    st.session_state.media = {}  # 録画本体（このセッションのメモリにだけ保持）
    for k in list(st.session_state.keys()):
        if str(k).startswith(("sel_", "ed_", "form_")):
            del st.session_state[k]


def user_name() -> str:
    return st.session_state.get("user_name", "").strip()


def goto(key: str) -> None:
    if key in PAGES:
        st.switch_page(PAGES[key])


def is_demo() -> bool:
    p = project()
    return bool(p and p["project"].get("demo_id"))


def product_id() -> str | None:
    p = project()
    prod = primary_product(p) if p else None
    return prod["id"] if prod else None


def flash(msg: str, kind: str = "success") -> None:
    """次の再描画で表示するメッセージ。"""
    st.session_state.setdefault("_flash", []).append((kind, msg))


def show_flash() -> None:
    for kind, msg in st.session_state.pop("_flash", []):
        getattr(st, kind)(msg)


def require_project() -> dict | None:
    p = project()
    if p is None:
        st.info("案件が開かれていません。ホームでデモを選ぶか、新しい案件を作成・保存案件を読み込んでください。")
        if st.button("ホームへ", icon=":material/home:"):
            goto("home")
    return p
