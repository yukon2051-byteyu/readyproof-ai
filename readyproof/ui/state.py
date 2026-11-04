"""画面の状態（利用者ごとのセッション）と共通操作。

st.session_state は閲覧者ごとに分かれるため、編集内容は他の利用者と混ざらない。
"""
from __future__ import annotations

import copy
import os
import re
import tempfile
import time
import uuid

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
    if s.budget.usage_hf_repo:
        from ..usage import HubLedger

        token = os.environ.get("RP_HF_TOKEN", "")
        return HubLedger(s.budget.usage_hf_repo, token) if token else None
    return Ledger(s.budget.usage_ledger_path)


def project() -> dict | None:
    return st.session_state.get("project")


def set_project(p: dict, demo_initial: dict | None = None) -> None:
    st.session_state.project = p
    st.session_state.demo_initial = copy.deepcopy(demo_initial) if demo_initial else None
    st.session_state.media = {}  # 録画本体（このセッションのメモリにだけ保持）
    for k in list(st.session_state.keys()):
        if str(k).startswith(("sel_", "ed_", "form_", "intake_")) or k in (
                "open_item", "focus_req", "edit_req", "pending_media"):
            del st.session_state[k]


def user_name() -> str:
    return st.session_state.get("user_name", "").strip() or "利用者"


# 以前の画面名 → 新しい4段階の画面
ALIASES = {"project": "input1", "sources": "input1", "requirements": "input2", "diagnosis": "result",
           "questions": "result"}


def goto(key: str) -> None:
    key = ALIASES.get(key, key)
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
        # 案件がないまま途中の画面のリンクを開いたときは、トップページへ自動で移る
        if "home" in PAGES:
            goto("home")
        st.info("案件が開かれていません。ホームでデモを選ぶか、新しい案件を作成してください。")
    return p


# ---------------- 接続が切れても作業を失わない（一時保存と復元） ----------------
_SESS_DIR = os.path.join(tempfile.gettempdir(), "readyproof_sessions")
_SID = re.compile(r"^[0-9a-f]{32}$")
_KEEP_SEC = 24 * 3600


def _cleanup() -> None:
    try:
        now = time.time()
        for name in os.listdir(_SESS_DIR):
            path = os.path.join(_SESS_DIR, name)
            if now - os.path.getmtime(path) > _KEEP_SEC:
                os.remove(path)
    except OSError:
        pass


def persist() -> None:
    """作業中の案件を一時ファイルに保存し、識別子（ランダム）をURLに付ける。毎回の画面更新の最後に呼ぶ。"""
    from ..export.jsonio import to_json_bytes

    p = project()
    if not p:
        return
    sid = st.session_state.get("_sid")
    if not sid:
        sid = st.session_state["_sid"] = uuid.uuid4().hex
    try:
        os.makedirs(_SESS_DIR, exist_ok=True)
        with open(os.path.join(_SESS_DIR, sid + ".json"), "wb") as f:
            f.write(to_json_bytes(p, include_unselected_notes=True))
        if st.query_params.get("s") != sid:
            st.query_params["s"] = sid
        if p["project"].get("demo_id") and st.query_params.get("demo") != p["project"]["demo_id"]:
            st.query_params["demo"] = p["project"]["demo_id"]
    except OSError:
        pass


def restore() -> None:
    """接続が切れて新しい画面になったとき、URLの識別子から作業を復元する。なければデモを開き直す。"""
    from ..export.jsonio import LoadError, from_json_bytes

    if project() is not None:
        return
    sid = st.query_params.get("s", "")
    if _SID.match(sid or ""):
        path = os.path.join(_SESS_DIR, sid + ".json")
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    st.session_state.project = from_json_bytes(f.read())
                st.session_state["_sid"] = sid
                st.session_state.setdefault("media", {})
                flash("接続が一度切れたため、作業を自動で復元しました。", "info")
                _cleanup()
                return
            except (OSError, LoadError):
                pass
    demo = st.query_params.get("demo", "")
    if demo in ("demo1", "demo2", "demo3"):
        from ..demos.builder import build

        p = build(demo)
        set_project(p, demo_initial=p)
        flash("接続が切れたため、デモを最初の状態で開き直しました。", "info")
