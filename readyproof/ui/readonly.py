"""デモ用の「見るだけ」範囲：囲んだ範囲の入力部品・決定ボタンをすべて非活性にする。

使い方：
    with readonly.scope(state.is_demo()):
        ...（この中のボタン・入力欄・確定・保存はデモでは押せない）

仕組み：Streamlit の入力部品（button・text_input など）に、範囲内だけ disabled=True を足す。
範囲の内外は利用者ごとの session_state で判定するため、ほかの利用者の画面には影響しない。
画面の移動・表示の切替（「詳しく確認する」など）は範囲の外に置く。
"""
from __future__ import annotations

import contextlib
import functools

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

_FLAG = "_rp_readonly"
WIDGETS = ["button", "text_input", "text_area", "selectbox", "radio", "checkbox", "toggle", "date_input",
           "number_input", "multiselect", "form_submit_button", "data_editor", "file_uploader"]


def _on() -> bool:
    try:
        return bool(st.session_state.get(_FLAG, False))
    except Exception:
        return False


def _wrap(orig):
    @functools.wraps(orig)
    def f(self, *a, **k):
        if _on():
            k["disabled"] = True
        return orig(self, *a, **k)

    f._rp_wrapped = True
    return f


def install() -> None:
    """起動時に1回だけ呼ぶ（何度呼んでも二重にはならない）。"""
    main = st._main
    for name in WIDGETS:
        orig = getattr(DeltaGenerator, name)
        if not getattr(orig, "_rp_wrapped", False):
            setattr(DeltaGenerator, name, _wrap(orig))
        # st.button などは起動時に作られた別の関数なので、こちらも差し替える
        setattr(st, name, getattr(main, name))


@contextlib.contextmanager
def scope(on: bool = True):
    prev = _on()
    st.session_state[_FLAG] = bool(on) or prev
    try:
        yield
    finally:
        st.session_state[_FLAG] = prev
